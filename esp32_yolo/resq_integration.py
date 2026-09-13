import sys
import os
import threading
import json
import socket
import time
import subprocess

try:
    from ultralytics import YOLO
except ImportError:
    print("Ultralytics is not installed.")
    sys.exit(1)

# Ensure the current directory is in path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

UDP_IP = "127.0.0.1"
UDP_PORT = 5005
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

def publish_results(results):
    if not results or len(results) == 0:
        return
    
    result = results[0]
    if result.boxes is None or len(result.boxes) == 0:
        return
    
    detections = []
    for i in range(len(result.boxes)):
        box = result.boxes[i]
        
        cls_id = int(box.cls[0].item())
        if cls_id != 0: # person
            continue
            
        conf = float(box.conf[0].item())
        
        # Get normalized coordinates xywh
        norm = box.xywhn[0].cpu().numpy()
        
        track_id = -1
        if result.boxes.id is not None:
            try:
                track_id = int(result.boxes.id[i].item())
            except Exception:
                pass
                
        detections.append({
            "x": float(norm[0]),
            "y": float(norm[1]),
            "w": float(norm[2]),
            "h": float(norm[3]),
            "confidence": conf,
            "track_id": track_id,
            "class_name": "person",
            "timestamp": time.time()
        })
        
    if detections:
        msg = json.dumps({
            "type": "detections",
            "data": detections,
            "timestamp": time.time()
        }).encode('utf-8')
        try:
            sock.sendto(msg, (UDP_IP, UDP_PORT))
        except Exception as e:
            pass # Silently fail if map server is not running

    # Also send the frame with YOLO bounding boxes to the Dashboard!
    try:
        import cv2
        # plot() returns the BGR image with boxes drawn
        annotated_frame = result.plot()
        # Resize to 320x240 to ensure it safely fits in a single UDP packet (< 64KB)
        small_frame = cv2.resize(annotated_frame, (320, 240))
        _, buffer = cv2.imencode('.jpg', small_frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
        sock.sendto(b"FRAME:" + buffer.tobytes(), (UDP_IP, UDP_PORT))
    except Exception as e:
        pass

# Hook YOLO methods
original_track = YOLO.track
original_predict = YOLO.predict

def hooked_track(self, *args, **kwargs):
    results = original_track(self, *args, **kwargs)
    publish_results(results)
    return results

def hooked_predict(self, *args, **kwargs):
    results = original_predict(self, *args, **kwargs)
    publish_results(results)
    return results

YOLO.track = hooked_track
YOLO.predict = hooked_predict

def start_map_server():
    server_path = os.path.join(os.path.dirname(__file__), 'map', 'server.py')
    # Run server in a separate process
    subprocess.Popen([sys.executable, server_path])

if __name__ == "__main__":
    print("="*60)
    print("STARTING RESQ-BOT INTEGRATION LAYER")
    print("Zero-modification YOLO hooks applied.")
    print("="*60)
    
    # Start map server in background
    start_map_server()
    
    # Import the user's existing script here so it uses the hooked YOLO class
    import ai_arm_controller
    
    # Run original system
    ai_arm_controller.main()
