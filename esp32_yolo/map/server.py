import os
import json
import asyncio
import socket
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import threading
import random

from tracker import SurvivorTracker
from logger import MissionLogger

app = FastAPI()

static_dir = os.path.join(os.path.dirname(__file__), 'static')
app.mount("/static", StaticFiles(directory=static_dir), name="static")

tracker = SurvivorTracker()
mission_logger = MissionLogger(os.path.join(os.path.dirname(__file__), '..', 'logs'))
connected_clients = set()

UDP_IP = "127.0.0.1"
UDP_PORT = 5005

latest_frame = None

@app.get("/")
async def root():
    return FileResponse(os.path.join(static_dir, 'index.html'))

@app.get("/video_feed")
async def video_feed():
    async def generate():
        while True:
            if latest_frame is not None:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + latest_frame + b'\r\n')
            await asyncio.sleep(0.05)
    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/api/firebase_coordinates")
async def get_firebase_coordinates():
    import urllib.request
    firebase_url = "https://newsdetection-7d302-default-rtdb.firebaseio.com/.json"
    try:
        req = urllib.request.Request(firebase_url, headers={'User-Agent': 'RESQ-BOT/1.0'})
        with urllib.request.urlopen(req, timeout=6) as response:
            raw_bytes = response.read()
            data = json.loads(raw_bytes.decode('utf-8'))
            return {"status": "success", "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    try:
        await websocket.send_json({
            "type": "full_state",
            "state": tracker.get_state()
        })
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                cmd = msg.get("command")
                if cmd == "BLOCK_PATH":
                    tracker.block_path()
                    mission_logger.queue.put_nowait({"timestamp": "N/A", "type": "SIM_COMMAND", "data": "Path Blocked"})
                elif cmd == "SPAWN_OBSTACLE":
                    rx, ry = tracker.robot_pose["x"], tracker.robot_pose["y"]
                    ox = rx + random.uniform(-10, 10)
                    oy = ry + random.uniform(-10, 10)
                    tracker.spawn_obstacle(ox, oy, size=random.randint(1, 3))
                elif cmd == "SPAWN_MOVING_HAZARD":
                    tracker.spawn_moving_hazard()
                    mission_logger.queue.put_nowait({"timestamp": "N/A", "type": "SIM_COMMAND", "data": "Spawned Moving Hazard"})
            except Exception as e:
                print(f"[WS ERROR] {e}")
                
    except WebSocketDisconnect:
        connected_clients.remove(websocket)

async def broadcast_state():
    while True:
        await asyncio.sleep(0.1) 
        if connected_clients:
            state = tracker.get_state()
            message = {"type": "update", "state": state}
            disconnected = set()
            for client in connected_clients:
                try:
                    await client.send_json(message)
                except Exception:
                    disconnected.add(client)
            for d in disconnected:
                connected_clients.remove(d)

def udp_listener_loop(loop):
    global latest_frame
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))
    sock.settimeout(1.0)
    print(f"[MAP SERVER] Listening for YOLO detections on UDP {UDP_PORT}")
    
    while True:
        try:
            data, addr = sock.recvfrom(65536)
            if data.startswith(b"FRAME:"):
                latest_frame = data[6:]
                continue
                
            msg = json.loads(data.decode('utf-8'))
            if msg.get("type") == "detections":
                detections = msg.get("data", [])
                tracker.update(detections)
                for det in detections:
                    mission_logger.log_detection(det)
                    
        except socket.timeout:
            tracker.update([])
        except Exception as e:
            print(f"[MAP SERVER] UDP Error: {e}")

@app.on_event("startup")
async def startup_event():
    loop = asyncio.get_running_loop()
    threading.Thread(target=udp_listener_loop, args=(loop,), daemon=True).start()
    asyncio.create_task(broadcast_state())
    mission_logger.start()

@app.on_event("shutdown")
async def shutdown_event():
    mission_logger.stop()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
