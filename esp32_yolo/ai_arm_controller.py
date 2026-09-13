"""
====================================================================
AI RESCUE ROBOT MASTER CONTROLLER
====================================================================

SYSTEM
--------------------------------------------------------------------
ESP32-CAM
    |
    | MJPEG HTTP
    v
Laptop Python + YOLO
    |
    +---------------- TCP 5000 ----------------> ESP32 ARM
    |
    +---------------- TCP 5001 ----------------> ESP32 MOTOR

NETWORK
--------------------------------------------------------------------
Laptop       : 10.75.112.158
ESP32-CAM    : 10.75.112.208
ESP32-ARM    : 10.75.112.207
ESP32-MOTOR   : 10.75.112.206
Gateway      : 10.75.112.77
Subnet       : 255.255.255.0

WIFI
--------------------------------------------------------------------
SSID         : Gtech1
Password     : 123456789

CAMERA
--------------------------------------------------------------------
Stream       : http://10.75.112.208/stream
Status       : http://10.75.112.208/status

ARM
--------------------------------------------------------------------
TCP          : 10.75.112.207:5000
HTTP         : http://10.75.112.207/

MOTOR
--------------------------------------------------------------------
TCP          : 10.75.112.206:5001
HTTP         : http://10.75.112.206/

MASTER DASHBOARD
--------------------------------------------------------------------
http://10.75.112.158:8080/

====================================================================
"""

import cv2
import json
import math
import os
import socket
import threading
import time

from dataclasses import dataclass, asdict
from typing import Optional, Tuple

import numpy as np


# ====================================================================
# YOLO
# ====================================================================

try:
    from ultralytics import YOLO
except ImportError:
    raise SystemExit(
        "\nUltralytics is not installed.\n"
        "Install with:\n"
        "pip install ultralytics\n"
    )


# ====================================================================
# NETWORK CONFIGURATION
# ====================================================================

WIFI_SSID = "Gtech1"
WIFI_PASSWORD = "123456789"

LAPTOP_IP = "10.75.112.158"

CAMERA_IP = "10.75.112.208"
CAMERA_STREAM = f"http://{CAMERA_IP}/stream"
CAMERA_STATUS = f"http://{CAMERA_IP}/status"

ARM_IP = "10.75.112.207"
ARM_PORT = 5000

MOTOR_IP = "10.75.112.206"
MOTOR_PORT = 5001

DASHBOARD_HOST = "0.0.0.0"
DASHBOARD_PORT = 8080


# ====================================================================
# YOLO CONFIGURATION
# ====================================================================

MODEL_PATH = "yolo26m-pose.pt"

PERSON_CLASS_ID = 0

CONFIDENCE_THRESHOLD = 0.45
IOU_THRESHOLD = 0.45

MAX_DETECTIONS = 10

USE_TRACKING = True

YOLO_IMAGE_SIZE = 640

YOLO_DEVICE = "auto"


# ====================================================================
# TARGET FILTERING
# ====================================================================

TARGET_CONFIRM_FRAMES = 2

TARGET_LOST_FRAMES = 8

SMOOTHING_ALPHA = 0.35

MIN_BOX_WIDTH = 20
MIN_BOX_HEIGHT = 40


# ====================================================================
# ARM CONFIGURATION
# ====================================================================

TARGET_SEND_INTERVAL = 0.06

ARM_HEARTBEAT_INTERVAL = 0.25

ARM_RECONNECT_INTERVAL = 1.0

ARM_CONNECT_TIMEOUT = 2.0

ARM_SOCKET_TIMEOUT = 1.0


# ====================================================================
# MOTOR CONFIGURATION
# ====================================================================

MOTOR_RECONNECT_INTERVAL = 1.0

MOTOR_CONNECT_TIMEOUT = 2.0

MOTOR_SOCKET_TIMEOUT = 1.0

MOTOR_HEARTBEAT_INTERVAL = 0.25

MOTOR_MAX_SPEED = 255

MOTOR_DEFAULT_SPEED = 255


# ====================================================================
# AUTO NAVIGATION
# ====================================================================

AUTO_LEFT_THRESHOLD = 0.38

AUTO_RIGHT_THRESHOLD = 0.62

AUTO_CENTER_MIN = 0.43
AUTO_CENTER_MAX = 0.57

AUTO_HOLD_HEIGHT = 0.62

AUTO_APPROACH_HEIGHT = 0.15

AUTO_FORWARD_SPEED_FAR = 255

AUTO_FORWARD_SPEED_MEDIUM = 220

AUTO_FORWARD_SPEED_NEAR = 180

AUTO_TURN_SPEED = 210


# ====================================================================
# DATA STRUCTURES
# ====================================================================

@dataclass
class Target:
    x: float = 0.5
    y: float = 0.5
    w: float = 0.0
    h: float = 0.0
    confidence: float = 0.0
    class_id: int = 0
    class_name: str = "person"
    track_id: int = -1

    @property
    def valid(self) -> bool:
        return (
            self.w > 0.0
            and self.h > 0.0
            and self.confidence >= CONFIDENCE_THRESHOLD
        )


@dataclass
class SystemState:
    mode: str = "AUTO"

    emergency_stop: bool = False

    target_present: bool = False

    target_x: float = 0.5
    target_y: float = 0.5
    target_w: float = 0.0
    target_h: float = 0.0
    target_confidence: float = 0.0
    target_track_id: int = -1

    arm_connected: bool = False
    motor_connected: bool = False
    camera_connected: bool = False

    arm_action: str = "STOP"
    motor_action: str = "STOP"

    motor_speed: int = MOTOR_DEFAULT_SPEED

    fps: float = 0.0

    processed_frames: int = 0

    last_update: float = 0.0


# ====================================================================
# GLOBAL SYSTEM STATE
# ====================================================================

state = SystemState()

state_lock = threading.Lock()


# ====================================================================
# HELPER FUNCTIONS
# ====================================================================

def update_state(**kwargs):

    with state_lock:

        for key, value in kwargs.items():

            if hasattr(state, key):
                setattr(state, key, value)

        state.last_update = time.time()


def get_state_dict():

    with state_lock:

        data = asdict(state)

    return data


def clamp(value, minimum, maximum):

    return max(
        minimum,
        min(maximum, value)
    )


# ====================================================================
# GENERIC TCP JSON CLIENT
# ====================================================================

class TCPJsonClient:

    def __init__(
        self,
        host: str,
        port: int,
        name: str,
        reconnect_interval: float = 1.0,
        connect_timeout: float = 2.0,
        socket_timeout: float = 1.0,
    ):

        self.host = host
        self.port = port
        self.name = name

        self.reconnect_interval = reconnect_interval

        self.connect_timeout = connect_timeout

        self.socket_timeout = socket_timeout

        self.sock: Optional[socket.socket] = None

        self.lock = threading.RLock()

        self.connected = False

        self.running = False

        self.last_connect_attempt = 0.0

        self.thread: Optional[threading.Thread] = None

    # ----------------------------------------------------------------
    # START
    # ----------------------------------------------------------------

    def start(self):

        if self.running:
            return

        self.running = True

        self.thread = threading.Thread(
            target=self._connection_loop,
            daemon=True,
            name=f"{self.name}-Connection"
        )

        self.thread.start()

    # ----------------------------------------------------------------
    # STOP
    # ----------------------------------------------------------------

    def stop(self):

        self.running = False

        self.disconnect()

    # ----------------------------------------------------------------
    # CONNECT
    # ----------------------------------------------------------------

    def connect(self):

        now = time.monotonic()

        if (
            now - self.last_connect_attempt
            < self.reconnect_interval
        ):
            return False

        self.last_connect_attempt = now

        self.disconnect()

        sock = None

        try:

            print(
                f"[{self.name}] Connecting "
                f"to {self.host}:{self.port}"
            )

            sock = socket.socket(
                socket.AF_INET,
                socket.SOCK_STREAM
            )

            sock.setsockopt(
                socket.IPPROTO_TCP,
                socket.TCP_NODELAY,
                1
            )

            sock.settimeout(
                self.connect_timeout
            )

            sock.connect(
                (
                    self.host,
                    self.port
                )
            )

            sock.settimeout(
                self.socket_timeout
            )

            with self.lock:

                self.sock = sock

                self.connected = True

            print(
                f"[{self.name}] CONNECTED"
            )

            return True

        except Exception as exc:

            print(
                f"[{self.name}] "
                f"Connection failed: {exc}"
            )

            if sock is not None:

                try:
                    sock.close()
                except Exception:
                    pass

            return False

    # ----------------------------------------------------------------
    # DISCONNECT
    # ----------------------------------------------------------------

    def disconnect(self):

        with self.lock:

            sock = self.sock

            self.sock = None

            self.connected = False

        if sock is not None:

            try:
                sock.shutdown(
                    socket.SHUT_RDWR
                )
            except Exception:
                pass

            try:
                sock.close()
            except Exception:
                pass

    # ----------------------------------------------------------------
    # SEND JSON
    # ----------------------------------------------------------------

    def send_json(self, message: dict):

        payload = (
            json.dumps(
                message,
                separators=(",", ":")
            )
            + "\n"
        ).encode("utf-8")

        with self.lock:

            if self.sock is None:

                self.connected = False

                return False

            try:

                self.sock.sendall(
                    payload
                )

                return True

            except Exception as exc:

                print(
                    f"[{self.name}] "
                    f"Send error: {exc}"
                )

                self.connected = False

                try:
                    self.sock.close()
                except Exception:
                    pass

                self.sock = None

                return False

    # ----------------------------------------------------------------
    # CONNECTION LOOP
    # ----------------------------------------------------------------

    def _connection_loop(self):

        while self.running:

            if not self.connected:

                self.connect()

            time.sleep(0.01)


# ====================================================================
# ARM CLIENT
# ====================================================================

class ArmClient(TCPJsonClient):

    def __init__(self):

        super().__init__(
            ARM_IP,
            ARM_PORT,
            "ARM",
            ARM_RECONNECT_INTERVAL,
            ARM_CONNECT_TIMEOUT,
            ARM_SOCKET_TIMEOUT
        )

        self.last_heartbeat = 0.0

    # ----------------------------------------------------------------
    # CONNECTION LOOP
    # ----------------------------------------------------------------

    def _connection_loop(self):

        while self.running:

            if not self.connected:

                if self.connect():

                    self.send_json({
                        "type": "ai_mode"
                    })

            now = time.monotonic()

            if (
                self.connected
                and
                now - self.last_heartbeat
                >= ARM_HEARTBEAT_INTERVAL
            ):

                if self.send_json({
                    "type": "heartbeat"
                }):

                    self.last_heartbeat = now

            update_state(
                arm_connected=self.connected
            )

            time.sleep(0.01)

    # ----------------------------------------------------------------
    # AI MODE
    # ----------------------------------------------------------------

    def ai_mode(self):

        self.send_json({
            "type": "ai_mode"
        })

    # ----------------------------------------------------------------
    # STOP
    # ----------------------------------------------------------------

    def stop_arm(self):

        self.send_json({
            "type": "stop"
        })

    # ----------------------------------------------------------------
    # RESUME
    # ----------------------------------------------------------------

    def resume_arm(self):

        self.send_json({
            "type": "resume"
        })

    # ----------------------------------------------------------------
    # HOME
    # ----------------------------------------------------------------

    def home_arm(self):

        self.send_json({
            "type": "home"
        })

    # ----------------------------------------------------------------
    # TARGET
    # ----------------------------------------------------------------

    def send_target(
        self,
        target: Target,
        action: str
    ):

        message = {

            "type": "target",

            "x": round(
                clamp(
                    target.x,
                    0.0,
                    1.0
                ),
                4
            ),

            "y": round(
                clamp(
                    target.y,
                    0.0,
                    1.0
                ),
                4
            ),

            "w": round(
                clamp(
                    target.w,
                    0.0,
                    1.0
                ),
                4
            ),

            "h": round(
                clamp(
                    target.h,
                    0.0,
                    1.0
                ),
                4
            ),

            "confidence": round(
                clamp(
                    target.confidence,
                    0.0,
                    1.0
                ),
                4
            ),

            "class": target.class_name,

            "class_id": int(
                target.class_id
            ),

            "track_id": int(
                target.track_id
            ),

            "action": action.upper()
        }

        return self.send_json(message)

    # ----------------------------------------------------------------
    # NO TARGET
    # ----------------------------------------------------------------

    def send_no_target(self):

        return self.send_json({

            "type": "target",

            "x": 0.5,
            "y": 0.5,

            "w": 0.0,
            "h": 0.0,

            "confidence": 0.0,

            "class": "none",

            "class_id": -1,

            "track_id": -1,

            "action": "STOP"
        })

    # ----------------------------------------------------------------
    # SERVO ANGLE
    # ----------------------------------------------------------------

    def servo_angle(
        self,
        name: str,
        angle: float
    ):

        return self.send_json({

            "type": "servo",

            "name": name,

            "angle": float(angle)
        })

    # ----------------------------------------------------------------
    # SERVO DELTA
    # ----------------------------------------------------------------

    def servo_delta(
        self,
        name: str,
        delta: float
    ):

        return self.send_json({

            "type": "move",

            "name": name,

            "delta": float(delta)
        })


# ====================================================================
# MOTOR CLIENT
# ====================================================================

class MotorClient(TCPJsonClient):

    def __init__(self):

        super().__init__(
            MOTOR_IP,
            MOTOR_PORT,
            "MOTOR",
            MOTOR_RECONNECT_INTERVAL,
            MOTOR_CONNECT_TIMEOUT,
            MOTOR_SOCKET_TIMEOUT
        )

        self.last_heartbeat = 0.0

        self.last_command = None

        self.last_speed = MOTOR_DEFAULT_SPEED

        self.command_lock = threading.RLock()

    # ----------------------------------------------------------------
    # CONNECTION LOOP
    # ----------------------------------------------------------------

    def _connection_loop(self):

        while self.running:

            if not self.connected:

                self.connect()

            now = time.monotonic()

            if (
                self.connected
                and
                now - self.last_heartbeat
                >= MOTOR_HEARTBEAT_INTERVAL
            ):

                if self.send_json({
                    "type": "heartbeat"
                }):

                    self.last_heartbeat = now

            update_state(
                motor_connected=self.connected
            )

            time.sleep(0.01)

    # ----------------------------------------------------------------
    # MOTOR COMMAND
    # ----------------------------------------------------------------

    def command(
        self,
        command: str,
        speed: int = MOTOR_DEFAULT_SPEED,
        force: bool = False
    ):

        command = command.upper()

        speed = int(
            clamp(
                speed,
                0,
                MOTOR_MAX_SPEED
            )
        )

        with self.command_lock:

            current = (
                command,
                speed
            )

            if (
                not force
                and
                current == self.last_command
            ):
                return True

            success = self.send_json({

                "type": "motor",

                "command": command,

                "speed": speed
            })

            if success:

                self.last_command = current

                self.last_speed = speed

                update_state(
                    motor_action=command,
                    motor_speed=speed
                )

            return success

    # ----------------------------------------------------------------
    # STOP
    # ----------------------------------------------------------------

    def stop_motor(self, force=True):

        return self.command(
            "STOP",
            0,
            force
        )


# ====================================================================
# CAMERA STREAM
# ====================================================================

class CameraStream:
    """
    Robust ESP32-CAM MJPEG reader.

    The ESP32-CAM exposes an HTTP multipart MJPEG stream. Reading the
    HTTP byte stream directly avoids OpenCV/FFmpeg failing to open the
    multipart HTTP URL on some Windows installations.
    """

    def __init__(self, url):
        self.url = url
        self.capture = None
        self.running = False
        self.frame = None
        self.lock = threading.RLock()
        self.thread = None

        self.last_frame_time = 0.0
        self.last_error_print = 0.0
        self.connection_failures = 0

    # ----------------------------------------------------------------
    # START
    # ----------------------------------------------------------------
    def start(self):
        if self.running:
            return

        self.running = True

        self.thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
            name="CameraStream"
        )

        self.thread.start()

    # ----------------------------------------------------------------
    # STOP
    # ----------------------------------------------------------------
    def stop(self):
        self.running = False

        if self.capture is not None:
            try:
                self.capture.close()
            except Exception:
                pass

        self.capture = None

    # ----------------------------------------------------------------
    # GET FRAME
    # ----------------------------------------------------------------
    def get_frame(self):
        with self.lock:
            if self.frame is None:
                return None

            return self.frame.copy()

    # ----------------------------------------------------------------
    # LOG ERROR
    # ----------------------------------------------------------------
    def _log_error(self, message):
        now = time.monotonic()

        if now - self.last_error_print >= 2.0:
            print(f"[CAMERA] {message}")
            self.last_error_print = now

    # ----------------------------------------------------------------
    # MJPEG HTTP LOOP
    # ----------------------------------------------------------------
    def _capture_loop(self):
        import urllib.request
        import urllib.error

        while self.running:
            response = None

            try:
                print(
                    f"[CAMERA] Connecting to ESP32-CAM: {self.url}"
                )

                request = urllib.request.Request(
                    self.url,
                    headers={
                        "User-Agent": "AI-Rescue-Robot/1.0",
                        "Accept": "multipart/x-mixed-replace,image/jpeg,*/*",
                        "Connection": "keep-alive",
                    }
                )

                # ESP32-CAM MJPEG streams continuously. A moderate
                # socket timeout lets us detect a dead stream and reconnect.
                response = urllib.request.urlopen(
                    request,
                    timeout=8
                )

                content_type = response.headers.get(
                    "Content-Type",
                    ""
                )

                print(
                    f"[CAMERA] HTTP {getattr(response, 'status', 200)} "
                    f"{content_type}"
                )

                update_state(
                    camera_connected=True
                )

                print("[CAMERA] CONNECTED")

                buffer = bytearray()

                while self.running:
                    chunk = response.read(4096)

                    if not chunk:
                        raise ConnectionError(
                            "ESP32-CAM closed the MJPEG stream"
                        )

                    buffer.extend(chunk)

                    # Keep the buffer bounded if a malformed stream
                    # contains no JPEG markers.
                    if len(buffer) > 2 * 1024 * 1024:
                        soi = buffer.rfind(b"\xff\xd8")
                        if soi >= 0:
                            buffer = buffer[soi:]
                        else:
                            buffer.clear()

                    while True:
                        start_jpeg = buffer.find(b"\xff\xd8")

                        if start_jpeg < 0:
                            # Keep only a small tail because JPEG start
                            # markers are two bytes.
                            if len(buffer) > 4096:
                                buffer = buffer[-4096:]
                            break

                        end_jpeg = buffer.find(
                            b"\xff\xd9",
                            start_jpeg + 2
                        )

                        if end_jpeg < 0:
                            # Wait for the rest of this JPEG.
                            if start_jpeg > 0:
                                buffer = buffer[start_jpeg:]
                            break

                        end_jpeg += 2

                        jpeg_bytes = bytes(
                            buffer[start_jpeg:end_jpeg]
                        )

                        buffer = buffer[end_jpeg:]

                        array = np.frombuffer(
                            jpeg_bytes,
                            dtype=np.uint8
                        )

                        frame = cv2.imdecode(
                            array,
                            cv2.IMREAD_COLOR
                        )

                        if frame is None:
                            continue

                        with self.lock:
                            self.frame = frame
                            self.last_frame_time = (
                                time.monotonic()
                            )

                        update_state(
                            camera_connected=True
                        )

                # Normal loop exit.
                break

            except Exception as exc:
                self.connection_failures += 1

                self._log_error(
                    f"Stream error: {exc}"
                )

                update_state(
                    camera_connected=False
                )

                if response is not None:
                    try:
                        response.close()
                    except Exception:
                        pass

                time.sleep(
                    min(
                        3.0,
                        0.5 + 0.25 * self.connection_failures
                    )
                )

            finally:
                if response is not None:
                    try:
                        response.close()
                    except Exception:
                        pass

        update_state(
            camera_connected=False
        )


# ====================================================================
# CAMERA HEALTH CHECK
# ====================================================================

def check_camera_http():
    """
    Verify that the ESP32-CAM HTTP server is reachable before the
    MJPEG reader starts. This does not use OpenCV/FFmpeg.
    """
    import urllib.request

    print(
        f"[CAMERA] Checking HTTP server: {CAMERA_IP}"
    )

    try:
        request = urllib.request.Request(
            CAMERA_STATUS,
            headers={
                "User-Agent": "AI-Rescue-Robot/1.0"
            }
        )

        with urllib.request.urlopen(
            request,
            timeout=5
        ) as response:
            status_code = getattr(
                response,
                "status",
                200
            )

            body = response.read(512).decode(
                "utf-8",
                errors="replace"
            )

            print(
                f"[CAMERA] HTTP status: {status_code}"
            )

            if body:
                print(
                    f"[CAMERA] Status response: {body}"
                )

            return True

    except Exception as exc:
        print(
            f"[CAMERA] HTTP health check failed: {exc}"
        )
        print(
            f"[CAMERA] Verify that "
            f"http://{CAMERA_IP}/status "
            f"is reachable from this laptop."
        )
        return False


# ====================================================================
# FPS COUNTER
# ====================================================================

class FPSCounter:

    def __init__(self):

        self.last_time = time.monotonic()

        self.frames = 0

        self.fps = 0.0

    def update(self):

        self.frames += 1

        now = time.monotonic()

        elapsed = (
            now - self.last_time
        )

        if elapsed >= 1.0:

            self.fps = (
                self.frames / elapsed
            )

            self.frames = 0

            self.last_time = now

        return self.fps


# ====================================================================
# HUMAN TRACKER
# ====================================================================

class HumanTracker:

    def __init__(self):

        print()
        print("=" * 70)
        print("LOADING YOLO MODEL")
        print("=" * 70)

        if not os.path.exists(
            MODEL_PATH
        ):

            raise FileNotFoundError(
                f"YOLO model not found: "
                f"{MODEL_PATH}"
            )

        self.model = YOLO(
            MODEL_PATH
        )

        self.last_target = None

        self.lost_frames = 0

        self.confirmation_count = 0

        self.device = self._get_device()

        print(
            f"[YOLO] Device: {self.device}"
        )

    # ----------------------------------------------------------------
    # DEVICE
    # ----------------------------------------------------------------

    def _get_device(self):

        if YOLO_DEVICE != "auto":
            return YOLO_DEVICE

        try:

            import torch

            if torch.cuda.is_available():

                print(
                    "[YOLO] CUDA GPU detected"
                )

                return 0

        except Exception:
            pass

        print(
            "[YOLO] Using CPU"
        )

        return "cpu"

    # ----------------------------------------------------------------
    # PROCESS
    # ----------------------------------------------------------------

    def process(
        self,
        frame: np.ndarray
    ) -> Tuple[
        Optional[Target],
        np.ndarray
    ]:

        display = frame.copy()

        height, width = (
            frame.shape[:2]
        )

        try:

            if USE_TRACKING:

                results = self.model.track(

                    source=frame,

                    persist=True,

                    classes=[
                        PERSON_CLASS_ID
                    ],

                    conf=(
                        CONFIDENCE_THRESHOLD
                    ),

                    iou=IOU_THRESHOLD,

                    imgsz=YOLO_IMAGE_SIZE,

                    max_det=MAX_DETECTIONS,

                    device=self.device,

                    verbose=False
                )

            else:

                results = self.model.predict(

                    source=frame,

                    classes=[
                        PERSON_CLASS_ID
                    ],

                    conf=(
                        CONFIDENCE_THRESHOLD
                    ),

                    iou=IOU_THRESHOLD,

                    imgsz=YOLO_IMAGE_SIZE,

                    max_det=MAX_DETECTIONS,

                    device=self.device,

                    verbose=False
                )

        except Exception as exc:

            print(
                f"[YOLO] Inference error: "
                f"{exc}"
            )

            return (
                self.last_target,
                display
            )

        if not results:

            return self._no_detection(
                display
            )

        result = results[0]

        if result.boxes is None:

            return self._no_detection(
                display
            )

        boxes = result.boxes

        if len(boxes) == 0:

            return self._no_detection(
                display
            )

        candidates = []

        # ------------------------------------------------------------
        # BUILD CANDIDATES
        # ------------------------------------------------------------

        for i in range(
            len(boxes)
        ):

            box = boxes[i]

            try:

                confidence = float(
                    box.conf[0].item()
                )

                class_id = int(
                    box.cls[0].item()
                )

            except Exception:
                continue

            if class_id != PERSON_CLASS_ID:
                continue

            try:

                coords = (
                    box.xyxy[0]
                    .cpu()
                    .numpy()
                )

                x1, y1, x2, y2 = map(
                    int,
                    coords
                )

            except Exception:
                continue

            x1 = int(
                clamp(
                    x1,
                    0,
                    width - 1
                )
            )

            y1 = int(
                clamp(
                    y1,
                    0,
                    height - 1
                )
            )

            x2 = int(
                clamp(
                    x2,
                    0,
                    width - 1
                )
            )

            y2 = int(
                clamp(
                    y2,
                    0,
                    height - 1
                )
            )

            box_width = (
                x2 - x1
            )

            box_height = (
                y2 - y1
            )

            if (
                box_width
                < MIN_BOX_WIDTH
            ):
                continue

            if (
                box_height
                < MIN_BOX_HEIGHT
            ):
                continue

            track_id = -1

            if boxes.id is not None:

                try:

                    track_id = int(
                        boxes.id[i].item()
                    )

                except Exception:

                    track_id = -1

            area = (
                box_width
                * box_height
            )

            area_ratio = (
                area
                /
                float(width * height)
            )

            center_x = (
                (x1 + x2)
                /
                2.0
            )

            center_y = (
                (y1 + y2)
                /
                2.0
            )

            score = (
                confidence * 0.55
                +
                min(
                    area_ratio * 3.0,
                    1.0
                ) * 0.25
            )

            # --------------------------------------------------------
            # TRACK CONTINUITY
            # --------------------------------------------------------

            if self.last_target:

                previous_px_x = (
                    self.last_target.x
                    * width
                )

                previous_px_y = (
                    self.last_target.y
                    * height
                )

                distance = math.sqrt(

                    (
                        center_x
                        - previous_px_x
                    ) ** 2

                    +

                    (
                        center_y
                        - previous_px_y
                    ) ** 2
                )

                max_distance = math.sqrt(
                    width ** 2
                    +
                    height ** 2
                )

                proximity = (
                    1.0
                    -
                    min(
                        distance
                        /
                        max_distance,
                        1.0
                    )
                )

                score += (
                    proximity * 0.20
                )

            candidates.append({

                "x1": x1,
                "y1": y1,

                "x2": x2,
                "y2": y2,

                "confidence": confidence,

                "track_id": track_id,

                "score": score
            })

        if not candidates:

            return self._no_detection(
                display
            )

        # ------------------------------------------------------------
        # BEST TARGET
        # ------------------------------------------------------------

        best = max(
            candidates,
            key=lambda item: item["score"]
        )

        x1 = best["x1"]
        y1 = best["y1"]

        x2 = best["x2"]
        y2 = best["y2"]

        confidence = (
            best["confidence"]
        )

        track_id = (
            best["track_id"]
        )

        center_x = (
            (x1 + x2)
            /
            2.0
            /
            width
        )

        center_y = (
            (y1 + y2)
            /
            2.0
            /
            height
        )

        box_width = (
            (x2 - x1)
            /
            width
        )

        box_height = (
            (y2 - y1)
            /
            height
        )

        raw_target = Target(

            x=clamp(
                center_x,
                0.0,
                1.0
            ),

            y=clamp(
                center_y,
                0.0,
                1.0
            ),

            w=clamp(
                box_width,
                0.0,
                1.0
            ),

            h=clamp(
                box_height,
                0.0,
                1.0
            ),

            confidence=confidence,

            class_id=PERSON_CLASS_ID,

            class_name="person",

            track_id=track_id
        )

        # ------------------------------------------------------------
        # CONFIRMATION
        # ------------------------------------------------------------

        self.confirmation_count += 1

        self.lost_frames = 0

        if (
            self.confirmation_count
            < TARGET_CONFIRM_FRAMES
        ):

            if self.last_target:

                return (
                    self.last_target,
                    self._draw_target(
                        display,
                        x1,
                        y1,
                        x2,
                        y2,
                        raw_target
                    )
                )

        # ------------------------------------------------------------
        # SMOOTH TARGET
        # ------------------------------------------------------------

        if self.last_target is None:

            smoothed = raw_target

        else:

            alpha = (
                SMOOTHING_ALPHA
            )

            smoothed = Target(

                x=(
                    alpha * raw_target.x
                    +
                    (1 - alpha)
                    * self.last_target.x
                ),

                y=(
                    alpha * raw_target.y
                    +
                    (1 - alpha)
                    * self.last_target.y
                ),

                w=(
                    alpha * raw_target.w
                    +
                    (1 - alpha)
                    * self.last_target.w
                ),

                h=(
                    alpha * raw_target.h
                    +
                    (1 - alpha)
                    * self.last_target.h
                ),

                confidence=(
                    alpha
                    * raw_target.confidence
                    +
                    (1 - alpha)
                    * self.last_target.confidence
                ),

                class_id=(
                    raw_target.class_id
                ),

                class_name="person",

                track_id=track_id
            )

        self.last_target = smoothed

        # ------------------------------------------------------------
        # DRAW
        # ------------------------------------------------------------

        display = self._draw_target(

            display,

            x1,
            y1,
            x2,
            y2,

            smoothed
        )

        return (
            smoothed,
            display
        )

    # ----------------------------------------------------------------
    # NO DETECTION
    # ----------------------------------------------------------------

    def _no_detection(
        self,
        display
    ):

        self.lost_frames += 1

        if (
            self.lost_frames
            >= TARGET_LOST_FRAMES
        ):

            self.last_target = None

            self.confirmation_count = 0

            return (
                None,
                display
            )

        return (
            self.last_target,
            display
        )

    # ----------------------------------------------------------------
    # DRAW TARGET
    # ----------------------------------------------------------------

    def _draw_target(
        self,
        frame,
        x1,
        y1,
        x2,
        y2,
        target
    ):

        cv2.rectangle(

            frame,

            (x1, y1),

            (x2, y2),

            (0, 255, 0),

            2
        )

        cx = int(
            target.x
            * frame.shape[1]
        )

        cy = int(
            target.y
            * frame.shape[0]
        )

        cv2.circle(

            frame,

            (cx, cy),

            6,

            (0, 255, 255),

            -1
        )

        label = (

            f"PERSON "
            f"{target.confidence:.2f}"
        )

        if target.track_id >= 0:

            label += (
                f" ID:{target.track_id}"
            )

        cv2.putText(

            frame,

            label,

            (x1, max(25, y1 - 8)),

            cv2.FONT_HERSHEY_SIMPLEX,

            0.6,

            (0, 255, 0),

            2
        )

        return frame


# ====================================================================
# AUTO ARM ACTION
# ====================================================================

def calculate_arm_action(
    target: Optional[Target]
):

    if (
        target is None
        or not target.valid
    ):

        return "STOP"

    x = target.x
    y = target.y
    h = target.h

    centered = (

        AUTO_CENTER_MIN
        <= x
        <= AUTO_CENTER_MAX

        and

        AUTO_CENTER_MIN
        <= y
        <= AUTO_CENTER_MAX
    )

    if centered:

        if h >= AUTO_HOLD_HEIGHT:

            return "HOLD"

        if h >= AUTO_APPROACH_HEIGHT:

            return "APPROACH"

    return "TRACK"


# ====================================================================
# AUTO MOTOR ACTION
# ====================================================================

def calculate_motor_action(
    target: Optional[Target]
):

    if (
        target is None
        or not target.valid
    ):

        return (
            "STOP",
            0
        )

    x = target.x

    h = target.h

    # ------------------------------------------------------------
    # PERSON TOO FAR LEFT
    # ------------------------------------------------------------

    if x < AUTO_LEFT_THRESHOLD:

        return (
            "LEFT",
            AUTO_TURN_SPEED
        )

    # ------------------------------------------------------------
    # PERSON TOO FAR RIGHT
    # ------------------------------------------------------------

    if x > AUTO_RIGHT_THRESHOLD:

        return (
            "RIGHT",
            AUTO_TURN_SPEED
        )

    # ------------------------------------------------------------
    # PERSON CENTERED
    # ------------------------------------------------------------

    if (
        AUTO_CENTER_MIN
        <= x
        <= AUTO_CENTER_MAX
    ):

        # Close enough.
        if h >= AUTO_HOLD_HEIGHT:

            return (
                "STOP",
                0
            )

        # Very far away.
        if h < 0.25:

            return (
                "FORWARD",
                AUTO_FORWARD_SPEED_FAR
            )

        # Medium distance.
        if h < 0.40:

            return (
                "FORWARD",
                AUTO_FORWARD_SPEED_MEDIUM
            )

        # Near.
        return (
            "FORWARD",
            AUTO_FORWARD_SPEED_NEAR
        )

    # ------------------------------------------------------------
    # FALLBACK
    # ------------------------------------------------------------

    return (
        "STOP",
        0
    )


# ====================================================================
# DASHBOARD HTML
# ====================================================================

DASHBOARD_HTML = r"""
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>AI Rescue Robot Control</title>

<style>

* {
    box-sizing: border-box;
}

body {

    margin: 0;

    font-family:
        Arial,
        Helvetica,
        sans-serif;

    background: #0b0f14;

    color: #f1f5f9;
}

header {

    padding: 18px;

    background: #111827;

    border-bottom:
        1px solid #263244;
}

header h1 {

    margin: 0;

    font-size: 24px;
}

header p {

    margin:
        6px 0 0 0;

    color: #94a3b8;
}

.container {

    max-width: 1500px;

    margin: auto;

    padding: 16px;
}

.grid {

    display: grid;

    grid-template-columns:
        2fr 1fr;

    gap: 16px;
}

.card {

    background: #111827;

    border:
        1px solid #263244;

    border-radius: 12px;

    padding: 16px;

    margin-bottom: 16px;
}

.card h2 {

    margin-top: 0;

    font-size: 18px;
}

.camera {

    width: 100%;

    min-height: 420px;

    object-fit: contain;

    background: #000;

    border-radius: 8px;
}

.status-grid {

    display: grid;

    grid-template-columns:
        repeat(3, 1fr);

    gap: 10px;
}

.status {

    padding: 12px;

    background: #0b1220;

    border-radius: 8px;
}

.status-label {

    font-size: 12px;

    color: #94a3b8;

    margin-bottom: 5px;
}

.status-value {

    font-size: 16px;

    font-weight: bold;
}

.ok {
    color: #4ade80;
}

.bad {
    color: #f87171;
}

.warn {
    color: #fbbf24;
}

.info {
    color: #60a5fa;
}

button {

    border: none;

    border-radius: 8px;

    padding: 14px;

    font-size: 15px;

    font-weight: bold;

    cursor: pointer;

    background: #263244;

    color: white;

    user-select: none;

    touch-action: manipulation;
}

button:hover {

    filter: brightness(1.15);
}

button:active {

    transform: scale(0.98);
}

.mode-row {

    display: grid;

    grid-template-columns:
        1fr 1fr;

    gap: 10px;
}

.auto {

    background: #2563eb;
}

.manual {

    background: #475569;
}

.stop {

    background: #dc2626;
}

.home {

    background: #7c3aed;
}

.resume {

    background: #059669;
}

.motor-grid {

    display: grid;

    grid-template-columns:
        repeat(3, 1fr);

    gap: 10px;

    max-width: 450px;

    margin: auto;
}

.motor-grid button {

    min-height: 70px;

    font-size: 22px;
}

.motor-forward {
    grid-column: 2;
}

.motor-left {
    grid-column: 1;
    grid-row: 2;
}

.motor-stop {
    grid-column: 2;
    grid-row: 2;
}

.motor-right {
    grid-column: 3;
    grid-row: 2;
}

.motor-backward {
    grid-column: 2;
    grid-row: 3;
}

.arm-grid {

    display: grid;

    grid-template-columns:
        repeat(2, 1fr);

    gap: 10px;
}

.slider {

    width: 100%;
}

.servo-row {

    display: grid;

    grid-template-columns:
        1fr 1fr 1fr;

    gap: 8px;

    align-items: center;

    margin-bottom: 10px;
}

.servo-name {

    font-weight: bold;
}

.target-box {

    background: #020617;

    border-radius: 8px;

    padding: 12px;

    font-family: monospace;

    white-space: pre-wrap;
}

.small {

    color: #94a3b8;

    font-size: 12px;
}

.danger-zone {

    border:
        1px solid #7f1d1d;
}

@media (max-width: 900px) {

    .grid {

        grid-template-columns: 1fr;
    }

    .camera {

        min-height: 250px;
    }

    .status-grid {

        grid-template-columns:
            repeat(2, 1fr);
    }
}

</style>

</head>


<body>

<header>

<h1>
    AI Rescue Robot Control Center
</h1>

<p>
    ESP32-CAM + YOLO + 5-Servo Arm + 4-Motor Drive
</p>

</header>


<div class="container">


<div class="grid">


<!-- ========================================================= -->
<!-- CAMERA -->
<!-- ========================================================= -->

<div>

<div class="card">

<h2>
    Live Camera + YOLO
</h2>

<img
    id="camera"
    class="camera"
    src="/processed_stream"
    alt="ESP32-CAM Stream"
>

</div>


<div class="card">

<h2>
    Target
</h2>

<div
    id="target"
    class="target-box"
>
Loading...
</div>

</div>

</div>


<!-- ========================================================= -->
<!-- SYSTEM STATUS -->
<!-- ========================================================= -->

<div>

<div class="card">

<h2>
    System Status
</h2>

<div class="status-grid">

<div class="status">

<div class="status-label">
MODE
</div>

<div
    id="mode"
    class="status-value"
>
-
</div>

</div>


<div class="status">

<div class="status-label">
CAMERA
</div>

<div
    id="cameraStatus"
    class="status-value"
>
-
</div>

</div>


<div class="status">

<div class="status-label">
ARM
</div>

<div
    id="armStatus"
    class="status-value"
>
-
</div>

</div>


<div class="status">

<div class="status-label">
MOTOR
</div>

<div
    id="motorStatus"
    class="status-value"
>
-
</div>

</div>


<div class="status">

<div class="status-label">
ARM ACTION
</div>

<div
    id="armAction"
    class="status-value"
>
-
</div>

</div>


<div class="status">

<div class="status-label">
MOTOR ACTION
</div>

<div
    id="motorAction"
    class="status-value"
>
-
</div>

</div>

</div>

</div>


<!-- ========================================================= -->
<!-- MODE -->
<!-- ========================================================= -->

<div class="card">

<h2>
    Control Mode
</h2>

<div class="mode-row">

<button
    class="auto"
    onclick="setMode('AUTO')"
>
AI AUTO
</button>

<button
    class="manual"
    onclick="setMode('MANUAL')"
>
MANUAL
</button>

</div>

</div>


<!-- ========================================================= -->
<!-- SAFETY -->
<!-- ========================================================= -->

<div class="card danger-zone">

<h2>
    Safety
</h2>

<div class="mode-row">

<button
    class="stop"
    onclick="emergencyStop()"
>
EMERGENCY STOP
</button>

<button
    class="resume"
    onclick="resumeSystem()"
>
RESUME
</button>

</div>

<br>

<button
    class="home"
    style="width:100%"
    onclick="homeArm()"
>
ARM HOME
</button>

</div>

</div>

</div>


<!-- ========================================================= -->
<!-- MOTOR CONTROL -->
<!-- ========================================================= -->

<div class="card">

<h2>
    Manual Motor Control
</h2>

<p class="small">
    Maximum speed: 255
</p>

<input
    id="speed"
    class="slider"
    type="range"
    min="0"
    max="255"
    value="255"
    oninput="updateSpeedLabel()"
>

<p>
Speed:
<span id="speedLabel">
255
</span>
</p>


<div class="motor-grid">

<button
    class="motor-forward"
    onpointerdown="motorPress('FORWARD')"
    onpointerup="motorRelease()"
    onpointercancel="motorRelease()"
    onpointerleave="motorRelease()"
>
▲
</button>


<button
    class="motor-left"
    onpointerdown="motorPress('LEFT')"
    onpointerup="motorRelease()"
    onpointercancel="motorRelease()"
    onpointerleave="motorRelease()"
>
◀
</button>


<button
    class="motor-stop stop"
    onclick="motorStop()"
>
STOP
</button>


<button
    class="motor-right"
    onpointerdown="motorPress('RIGHT')"
    onpointerup="motorRelease()"
    onpointercancel="motorRelease()"
    onpointerleave="motorRelease()"
>
▶
</button>


<button
    class="motor-backward"
    onpointerdown="motorPress('BACKWARD')"
    onpointerup="motorRelease()"
    onpointercancel="motorRelease()"
    onpointerleave="motorRelease()"
>
▼
</button>

</div>

</div>


<!-- ========================================================= -->
<!-- ARM CONTROL -->
<!-- ========================================================= -->

<div class="card">

<h2>
    Manual Robot Arm
</h2>


<div class="arm-grid">

<button
    onclick="servoMove('base', -2)"
>
BASE LEFT
</button>

<button
    onclick="servoMove('base', 2)"
>
BASE RIGHT
</button>


<button
    onclick="servoMove('shoulder', -2)"
>
SHOULDER UP
</button>

<button
    onclick="servoMove('shoulder', 2)"
>
SHOULDER DOWN
</button>


<button
    onclick="servoMove('elbow', -2)"
>
ELBOW UP
</button>

<button
    onclick="servoMove('elbow', 2)"
>
ELBOW DOWN
</button>


<button
    onclick="servoMove('head_up', -2)"
>
HEAD UP
</button>

<button
    onclick="servoMove('head_up', 2)"
>
HEAD DOWN
</button>


<button
    onclick="servoMove('head_turn', -2)"
>
HEAD LEFT
</button>

<button
    onclick="servoMove('head_turn', 2)"
>
HEAD RIGHT
</button>

</div>

</div>


<!-- ========================================================= -->
<!-- KEYBOARD -->
<!-- ========================================================= -->

<div class="card">

<h2>
    Keyboard Controls
</h2>

<div class="target-box">

W = Forward
S = Backward
A = Left
D = Right
X = Stop

1 = AUTO
2 = MANUAL

Q = Emergency Stop
R = Resume
H = Arm Home

J / L = Base
I / K = Shoulder
U / O = Elbow

Arrow Up / Down = Head Up/Down
Arrow Left / Right = Head Turn

</div>

</div>


</div>


<script>


// ============================================================
// API
// ============================================================

async function api(
    url,
    data = {}
) {

    try {

        const response =
            await fetch(
                url,
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify(data)
                }
            );

        return await response.json();

    } catch(error) {

        console.error(error);

        return {
            ok: false,
            error: String(error)
        };
    }
}


// ============================================================
// MODE
// ============================================================

async function setMode(mode) {

    await api(
        "/api/mode",
        {
            mode: mode
        }
    );
}


// ============================================================
// EMERGENCY STOP
// ============================================================

async function emergencyStop() {

    await api(
        "/api/emergency_stop"
    );
}


// ============================================================
// RESUME
// ============================================================

async function resumeSystem() {

    await api(
        "/api/resume"
    );
}


// ============================================================
// HOME
// ============================================================

async function homeArm() {

    await api(
        "/api/arm/home"
    );
}


// ============================================================
// MOTOR
// ============================================================

async function motorPress(
    command
) {

    const speed =
        parseInt(
            document
                .getElementById("speed")
                .value
        );

    await api(
        "/api/motor",
        {
            command: command,
            speed: speed
        }
    );
}


async function motorRelease() {

    await api(
        "/api/motor",
        {
            command: "STOP",
            speed: 0
        }
    );
}


async function motorStop() {

    await api(
        "/api/motor",
        {
            command: "STOP",
            speed: 0
        }
    );
}


// ============================================================
// SERVO
// ============================================================

async function servoMove(
    name,
    delta
) {

    await api(
        "/api/arm/move",
        {
            name: name,
            delta: delta
        }
    );
}


// ============================================================
// SPEED
// ============================================================

function updateSpeedLabel() {

    const value =
        document
            .getElementById("speed")
            .value;

    document
        .getElementById("speedLabel")
        .innerText = value;
}


// ============================================================
// STATUS
// ============================================================

async function updateStatus() {

    try {

        const response =
            await fetch(
                "/api/state",
                {
                    cache: "no-store"
                }
            );

        const data =
            await response.json();


        document
            .getElementById("mode")
            .innerText =
                data.emergency_stop
                ? "EMERGENCY STOP"
                : data.mode;


        setConnection(
            "cameraStatus",
            data.camera_connected
        );

        setConnection(
            "armStatus",
            data.arm_connected
        );

        setConnection(
            "motorStatus",
            data.motor_connected
        );


        document
            .getElementById("armAction")
            .innerText =
                data.arm_action;


        document
            .getElementById("motorAction")
            .innerText =
                data.motor_action;


        document
            .getElementById("target")
            .innerText =

            "TARGET: "
            +
            (
                data.target_present
                ? "PERSON"
                : "NONE"
            )

            +

            "\n\nX: "
            +
            data.target_x.toFixed(3)

            +

            "\nY: "
            +
            data.target_y.toFixed(3)

            +

            "\nW: "
            +
            data.target_w.toFixed(3)

            +

            "\nH: "
            +
            data.target_h.toFixed(3)

            +

            "\nCONFIDENCE: "
            +
            data.target_confidence.toFixed(3)

            +

            "\nTRACK ID: "
            +
            data.target_track_id

            +

            "\n\nFPS: "
            +
            data.fps.toFixed(1)

            +

            "\nMOTOR SPEED: "
            +
            data.motor_speed;

    } catch(error) {

        console.error(error);
    }
}


function setConnection(
    element,
    connected
) {

    const node =
        document.getElementById(
            element
        );

    node.innerText =
        connected
        ? "CONNECTED"
        : "OFFLINE";

    node.className =
        connected
        ? "status-value ok"
        : "status-value bad";
}


// ============================================================
// KEYBOARD
// ============================================================

let keyboardMotor = null;


document.addEventListener(
    "keydown",
    async function(event) {

        if (event.repeat) {
            return;
        }

        const key =
            event.key.toLowerCase();


        if (key === "w") {

            keyboardMotor = "FORWARD";

            await motorPress(
                "FORWARD"
            );

            return;
        }


        if (key === "s") {

            keyboardMotor = "BACKWARD";

            await motorPress(
                "BACKWARD"
            );

            return;
        }


        if (key === "a") {

            keyboardMotor = "LEFT";

            await motorPress(
                "LEFT"
            );

            return;
        }


        if (key === "d") {

            keyboardMotor = "RIGHT";

            await motorPress(
                "RIGHT"
            );

            return;
        }


        if (key === "x") {

            keyboardMotor = null;

            await motorStop();

            return;
        }


        if (key === "1") {

            await setMode("AUTO");

            return;
        }


        if (key === "2") {

            await setMode("MANUAL");

            return;
        }


        if (key === "q") {

            await emergencyStop();

            return;
        }


        if (key === "r") {

            await resumeSystem();

            return;
        }


        if (key === "h") {

            await homeArm();

            return;
        }


        if (key === "j") {

            await servoMove(
                "base",
                -2
            );

            return;
        }


        if (key === "l") {

            await servoMove(
                "base",
                2
            );

            return;
        }


        if (key === "i") {

            await servoMove(
                "shoulder",
                -2
            );

            return;
        }


        if (key === "k") {

            await servoMove(
                "shoulder",
                2
            );

            return;
        }


        if (key === "u") {

            await servoMove(
                "elbow",
                -2
            );

            return;
        }


        if (key === "o") {

            await servoMove(
                "elbow",
                2
            );

            return;
        }


        if (event.key === "ArrowUp") {

            event.preventDefault();

            await servoMove(
                "head_up",
                -2
            );

            return;
        }


        if (event.key === "ArrowDown") {

            event.preventDefault();

            await servoMove(
                "head_up",
                2
            );

            return;
        }


        if (event.key === "ArrowLeft") {

            event.preventDefault();

            await servoMove(
                "head_turn",
                -2
            );

            return;
        }


        if (event.key === "ArrowRight") {

            event.preventDefault();

            await servoMove(
                "head_turn",
                2
            );

            return;
        }

    }
);


// ============================================================
// KEYBOARD RELEASE
// ============================================================

document.addEventListener(
    "keyup",
    async function(event) {

        const key =
            event.key.toLowerCase();

        if (
            key === "w"
            ||
            key === "a"
            ||
            key === "s"
            ||
            key === "d"
        ) {

            keyboardMotor = null;

            await motorStop();
        }

    }
);


// ============================================================
// START
// ============================================================

setInterval(
    updateStatus,
    500
);

updateStatus();

updateSpeedLabel();


</script>

</body>

</html>
"""


# ====================================================================
# DASHBOARD HTTP SERVER
# ====================================================================

from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer
)


class DashboardHandler(
    BaseHTTPRequestHandler
):

    # ---------------------------------------------------------------
    # LOG
    # ---------------------------------------------------------------

    def log_message(
        self,
        format,
        *args
    ):

        return

    # ---------------------------------------------------------------
    # JSON RESPONSE
    # ---------------------------------------------------------------

    def send_json(
        self,
        payload,
        status_code=200
    ):

        body = json.dumps(
            payload
        ).encode("utf-8")

        self.send_response(
            status_code
        )

        self.send_header(
            "Content-Type",
            "application/json"
        )

        self.send_header(
            "Content-Length",
            str(len(body))
        )

        self.send_header(
            "Cache-Control",
            "no-store"
        )

        self.end_headers()

        self.wfile.write(body)

    # ---------------------------------------------------------------
    # READ JSON
    # ---------------------------------------------------------------

    def read_json(self):

        try:

            length = int(
                self.headers.get(
                    "Content-Length",
                    "0"
                )
            )

            if length <= 0:
                return {}

            raw = self.rfile.read(
                length
            )

            return json.loads(
                raw.decode("utf-8")
            )

        except Exception:

            return {}

    # ---------------------------------------------------------------
    # GET
    # ---------------------------------------------------------------

    def do_GET(self):

        if self.path == "/":

            body = (
                DASHBOARD_HTML
                .encode("utf-8")
            )

            self.send_response(200)

            self.send_header(
                "Content-Type",
                "text/html; charset=utf-8"
            )

            self.send_header(
                "Content-Length",
                str(len(body))
            )

            self.end_headers()

            self.wfile.write(body)

            return


        if self.path == "/api/state":

            self.send_json(
                get_state_dict()
            )

            return

        if self.path == "/processed_stream":
            self.handle_processed_stream()
            return


        self.send_json(
            {
                "ok": False,
                "error": "Not found"
            },
            404
        )

    # ---------------------------------------------------------------
    # POST
    # ---------------------------------------------------------------

    def handle_processed_stream(self):
        boundary = b"--frame\\r\\n"

        self.send_response(200)
        self.send_header(
            "Content-Type",
            "multipart/x-mixed-replace; boundary=frame"
        )
        self.send_header(
            "Cache-Control",
            "no-cache, no-store, must-revalidate"
        )
        self.send_header("Pragma", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        last_sequence = -1

        try:
            while running:
                with processed_frame_lock:
                    payload = processed_frame_jpeg
                    sequence = processed_frame_sequence

                if payload is None or sequence == last_sequence:
                    time.sleep(0.01)
                    continue

                self.wfile.write(boundary)
                self.wfile.write(b"Content-Type: image/jpeg\\r\\n")
                self.wfile.write(
                    f"Content-Length: {len(payload)}\\r\\n\\r\\n".encode("ascii")
                )
                self.wfile.write(payload)
                self.wfile.write(b"\\r\\n")
                self.wfile.flush()

                last_sequence = sequence

        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            print(f"[DASHBOARD] Processed stream closed: {exc}")


    def do_POST(self):

        data = self.read_json()

        # -----------------------------------------------------------
        # MODE
        # -----------------------------------------------------------

        if self.path == "/api/mode":

            mode = str(
                data.get(
                    "mode",
                    ""
                )
            ).upper()

            if mode not in (
                "AUTO",
                "MANUAL"
            ):

                self.send_json(
                    {
                        "ok": False,
                        "error":
                            "Invalid mode"
                    },
                    400
                )

                return

            if mode == "AUTO":

                update_state(
                    mode="AUTO",
                    emergency_stop=False
                )

                arm.ai_mode()

                motor.command(
                    "STOP",
                    0,
                    True
                )

            else:

                update_state(
                    mode="MANUAL"
                )

                motor.stop_motor(
                    True
                )

            self.send_json({
                "ok": True,
                "mode": mode
            })

            return


        # -----------------------------------------------------------
        # EMERGENCY STOP
        # -----------------------------------------------------------

        if (
            self.path
            == "/api/emergency_stop"
        ):

            update_state(
                emergency_stop=True
            )

            try:
                arm.stop_arm()
            except Exception:
                pass

            try:
                motor.stop_motor(True)
            except Exception:
                pass

            update_state(
                arm_action="STOP",
                motor_action="STOP",
                motor_speed=0
            )

            self.send_json({
                "ok": True
            })

            return


        # -----------------------------------------------------------
        # RESUME
        # -----------------------------------------------------------

        if self.path == "/api/resume":

            update_state(
                emergency_stop=False,
                mode="AUTO"
            )

            arm.resume_arm()

            motor.stop_motor(True)

            self.send_json({
                "ok": True
            })

            return


        # -----------------------------------------------------------
        # MOTOR
        # -----------------------------------------------------------

        if self.path == "/api/motor":

            if state.emergency_stop:

                self.send_json(
                    {
                        "ok": False,
                        "error":
                            "Emergency stop active"
                    },
                    409
                )

                return

            command = str(
                data.get(
                    "command",
                    "STOP"
                )
            ).upper()

            allowed = {
                "FORWARD",
                "BACKWARD",
                "LEFT",
                "RIGHT",
                "STOP"
            }

            if command not in allowed:

                self.send_json(
                    {
                        "ok": False,
                        "error":
                            "Invalid motor command"
                    },
                    400
                )

                return

            if state.mode != "MANUAL":

                self.send_json(
                    {
                        "ok": False,
                        "error":
                            "Switch to MANUAL mode"
                    },
                    409
                )

                return

            speed = int(
                clamp(
                    int(
                        data.get(
                            "speed",
                            MOTOR_DEFAULT_SPEED
                        )
                    ),
                    0,
                    MOTOR_MAX_SPEED
                )
            )

            if command == "STOP":
                speed = 0

            success = motor.command(
                command,
                speed,
                True
            )

            self.send_json({
                "ok": success,
                "command": command,
                "speed": speed
            })

            return


        # -----------------------------------------------------------
        # ARM MOVE
        # -----------------------------------------------------------

        if self.path == "/api/arm/move":

            if state.emergency_stop:

                self.send_json(
                    {
                        "ok": False,
                        "error":
                            "Emergency stop active"
                    },
                    409
                )

                return

            if state.mode != "MANUAL":

                self.send_json(
                    {
                        "ok": False,
                        "error":
                            "Switch to MANUAL mode"
                    },
                    409
                )

                return

            name = str(
                data.get(
                    "name",
                    ""
                )
            ).strip().lower()

            delta = float(
                data.get(
                    "delta",
                    0
                )
            )

            allowed = {
                "base",
                "shoulder",
                "elbow",
                "head_up",
                "head_turn"
            }

            if name not in allowed:

                self.send_json(
                    {
                        "ok": False,
                        "error":
                            "Invalid servo"
                    },
                    400
                )

                return

            success = arm.servo_delta(
                name,
                delta
            )

            self.send_json({
                "ok": success
            })

            return


        # -----------------------------------------------------------
        # ARM HOME
        # -----------------------------------------------------------

        if self.path == "/api/arm/home":

            if state.emergency_stop:

                self.send_json(
                    {
                        "ok": False,
                        "error":
                            "Emergency stop active"
                    },
                    409
                )

                return

            update_state(
                mode="MANUAL"
            )

            motor.stop_motor(True)

            success = arm.home_arm()

            self.send_json({
                "ok": success
            })

            return


        # -----------------------------------------------------------
        # UNKNOWN
        # -----------------------------------------------------------

        self.send_json(
            {
                "ok": False,
                "error": "Not found"
            },
            404
        )


# ====================================================================
# START DASHBOARD
# ====================================================================

def start_dashboard():

    server = ThreadingHTTPServer(
        (
            DASHBOARD_HOST,
            DASHBOARD_PORT
        ),
        DashboardHandler
    )

    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
        name="DashboardServer"
    )

    thread.start()

    print()
    print("=" * 70)
    print("MASTER DASHBOARD")
    print("=" * 70)
    print(
        f"http://{LAPTOP_IP}:{DASHBOARD_PORT}/"
    )
    print("=" * 70)

    return server


# ====================================================================
# DRAW SYSTEM DASHBOARD ON OPENCV
# ====================================================================

def draw_overlay(
    frame,
    target,
    fps
):

    height, width = (
        frame.shape[:2]
    )

    current_state = get_state_dict()

    # ---------------------------------------------------------------
    # MODE
    # ---------------------------------------------------------------

    cv2.putText(

        frame,

        (
            f"MODE: "
            f"{current_state['mode']}"
        ),

        (15, 30),

        cv2.FONT_HERSHEY_SIMPLEX,

        0.7,

        (255, 255, 255),

        2
    )

    # ---------------------------------------------------------------
    # FPS
    # ---------------------------------------------------------------

    cv2.putText(

        frame,

        f"FPS: {fps:.1f}",

        (15, 60),

        cv2.FONT_HERSHEY_SIMPLEX,

        0.6,

        (255, 255, 255),

        2
    )

    # ---------------------------------------------------------------
    # MOTOR
    # ---------------------------------------------------------------

    cv2.putText(

        frame,

        (
            f"MOTOR: "
            f"{current_state['motor_action']} "
            f"{current_state['motor_speed']}"
        ),

        (15, 90),

        cv2.FONT_HERSHEY_SIMPLEX,

        0.6,

        (255, 255, 255),

        2
    )

    # ---------------------------------------------------------------
    # ARM
    # ---------------------------------------------------------------

    cv2.putText(

        frame,

        (
            f"ARM: "
            f"{current_state['arm_action']}"
        ),

        (15, 120),

        cv2.FONT_HERSHEY_SIMPLEX,

        0.6,

        (255, 255, 255),

        2
    )

    # ---------------------------------------------------------------
    # TARGET
    # ---------------------------------------------------------------

    if target and target.valid:

        cv2.putText(

            frame,

            (
                f"TARGET "
                f"X:{target.x:.2f} "
                f"Y:{target.y:.2f} "
                f"H:{target.h:.2f}"
            ),

            (15, 150),

            cv2.FONT_HERSHEY_SIMPLEX,

            0.55,

            (0, 255, 0),

            2
        )

    else:

        cv2.putText(

            frame,

            "TARGET: NONE",

            (15, 150),

            cv2.FONT_HERSHEY_SIMPLEX,

            0.6,

            (0, 0, 255),

            2
        )

    # ---------------------------------------------------------------
    # CONNECTIONS
    # ---------------------------------------------------------------

    connection_text = (

        f"CAM:{'OK' if current_state['camera_connected'] else 'OFF'} "

        f"ARM:{'OK' if current_state['arm_connected'] else 'OFF'} "

        f"MOTOR:{'OK' if current_state['motor_connected'] else 'OFF'}"
    )

    cv2.putText(

        frame,

        connection_text,

        (15, 180),

        cv2.FONT_HERSHEY_SIMPLEX,

        0.5,

        (255, 255, 255),

        2
    )

    # ---------------------------------------------------------------
    # EMERGENCY
    # ---------------------------------------------------------------

    if current_state[
        "emergency_stop"
    ]:

        cv2.putText(

            frame,

            "!!! EMERGENCY STOP !!!",

            (
                width // 2 - 180,
                height - 30
            ),

            cv2.FONT_HERSHEY_SIMPLEX,

            0.8,

            (0, 0, 255),

            3
        )

    return frame


# ====================================================================
# AI CONTROL LOOP
# ====================================================================

def ai_control_loop(
    tracker,
    camera,
    fps_counter
):

    last_target_send = 0.0

    last_motor_command = None

    last_motor_command_time = 0.0

    last_target = None

    processed_frames = 0

    print(
        "[SYSTEM] AI control loop started"
    )

    while running:

        frame = camera.get_frame()

        if frame is None:

            time.sleep(0.01)

            continue

        processed_frames += 1

        current_state = (
            get_state_dict()
        )

        # -----------------------------------------------------------
        # AUTO MODE
        # -----------------------------------------------------------

        if (
            current_state["mode"]
            == "AUTO"
            and
            not current_state[
                "emergency_stop"
            ]
        ):

            target, display = (
                tracker.process(frame)
            )

            last_target = target

            # -------------------------------------------------------
            # FPS
            # -------------------------------------------------------

            fps = fps_counter.update()

            update_state(
                fps=fps,
                processed_frames=processed_frames
            )

            # -------------------------------------------------------
            # TARGET STATE
            # -------------------------------------------------------

            if target and target.valid:

                update_state(

                    target_present=True,

                    target_x=target.x,

                    target_y=target.y,

                    target_w=target.w,

                    target_h=target.h,

                    target_confidence=(
                        target.confidence
                    ),

                    target_track_id=(
                        target.track_id
                    )
                )

            else:

                update_state(

                    target_present=False,

                    target_x=0.5,

                    target_y=0.5,

                    target_w=0.0,

                    target_h=0.0,

                    target_confidence=0.0,

                    target_track_id=-1
                )

            # -------------------------------------------------------
            # ARM
            # -------------------------------------------------------

            arm_action = (
                calculate_arm_action(
                    target
                )
            )

            update_state(
                arm_action=arm_action
            )

            now = time.monotonic()

            if (
                now - last_target_send
                >= TARGET_SEND_INTERVAL
            ):

                if arm.connected:

                    if target and target.valid:

                        arm.send_target(
                            target,
                            arm_action
                        )

                    else:

                        arm.send_no_target()

                last_target_send = now

            # -------------------------------------------------------
            # MOTOR
            # -------------------------------------------------------

            motor_command, motor_speed = (
                calculate_motor_action(
                    target
                )
            )

            update_state(
                motor_action=motor_command,
                motor_speed=motor_speed
            )

            motor_state = (
                motor_command,
                motor_speed
            )

            # Send motor command when it changes.
            if (
                motor_state
                != last_motor_command
            ):

                motor.command(
                    motor_command,
                    motor_speed,
                    True
                )

                last_motor_command = (
                    motor_state
                )

                last_motor_command_time = (
                    now
                )

            # -------------------------------------------------------
            # MOTOR SAFETY REFRESH
            # -------------------------------------------------------

            elif (
                motor_command != "STOP"
                and
                now
                - last_motor_command_time
                > 0.8
            ):

                motor.command(
                    motor_command,
                    motor_speed,
                    True
                )

                last_motor_command_time = (
                    now
                )

        # -----------------------------------------------------------
        # MANUAL MODE
        # -----------------------------------------------------------

        else:

            fps = fps_counter.update()

            update_state(
                fps=fps,
                processed_frames=processed_frames
            )

            display = frame.copy()

            # In manual mode AI must not drive motors.
            if (
                current_state["mode"]
                == "MANUAL"
                and
                last_motor_command
                not in (
                    None,
                    ("STOP", 0)
                )
            ):

                motor.stop_motor(True)

                last_motor_command = (
                    "STOP",
                    0
                )

            # -------------------------------------------------------
            # STOPPED
            # -------------------------------------------------------

            if current_state[
                "emergency_stop"
            ]:

                if (
                    last_motor_command
                    != ("STOP", 0)
                ):

                    motor.stop_motor(
                        True
                    )

                    last_motor_command = (
                        "STOP",
                        0
                    )

        # -----------------------------------------------------------
        # DRAW
        # -----------------------------------------------------------

        display = draw_overlay(
            display,
            last_target,
            get_state_dict()["fps"]
        )

        # The browser must receive the YOLO-annotated frame, not the raw
        # ESP32-CAM stream, so detections are visible in the dashboard.
        update_processed_frame(display)

        cv2.imshow(
            "AI Rescue Robot",
            display
        )

        key = (
            cv2.waitKey(1)
            &
            0xFF
        )

        # -----------------------------------------------------------
        # QUIT
        # -----------------------------------------------------------

        if key == ord("q"):

            print(
                "[SYSTEM] Quit requested"
            )

            break

        # -----------------------------------------------------------
        # AUTO
        # -----------------------------------------------------------

        if key == ord("1"):

            update_state(
                mode="AUTO",
                emergency_stop=False
            )

            arm.ai_mode()

        # -----------------------------------------------------------
        # MANUAL
        # -----------------------------------------------------------

        elif key == ord("2"):

            update_state(
                mode="MANUAL"
            )

            motor.stop_motor(True)

        # -----------------------------------------------------------
        # EMERGENCY
        # -----------------------------------------------------------

        elif key == ord("x"):

            update_state(
                emergency_stop=True
            )

            arm.stop_arm()

            motor.stop_motor(True)

        # -----------------------------------------------------------
        # RESUME
        # -----------------------------------------------------------

        elif key == ord("r"):

            update_state(
                emergency_stop=False,
                mode="AUTO"
            )

            arm.resume_arm()

            motor.stop_motor(True)

        # -----------------------------------------------------------
        # HOME
        # -----------------------------------------------------------

        elif key == ord("h"):

            update_state(
                mode="MANUAL"
            )

            motor.stop_motor(True)

            arm.home_arm()

        # -----------------------------------------------------------
        # MANUAL MOTOR
        # -----------------------------------------------------------

        elif key == ord("w"):

            if (
                get_state_dict()["mode"]
                == "MANUAL"
            ):

                motor.command(
                    "FORWARD",
                    MOTOR_MAX_SPEED,
                    True
                )

        elif key == ord("s"):

            if (
                get_state_dict()["mode"]
                == "MANUAL"
            ):

                motor.command(
                    "BACKWARD",
                    MOTOR_MAX_SPEED,
                    True
                )

        elif key == ord("a"):

            if (
                get_state_dict()["mode"]
                == "MANUAL"
            ):

                motor.command(
                    "LEFT",
                    MOTOR_MAX_SPEED,
                    True
                )

        elif key == ord("d"):

            if (
                get_state_dict()["mode"]
                == "MANUAL"
            ):

                motor.command(
                    "RIGHT",
                    MOTOR_MAX_SPEED,
                    True
                )

        elif key == ord(" "):

            motor.stop_motor(True)


# ====================================================================
# GLOBAL RUNNING FLAG
# ====================================================================

running = True


# ====================================================================
# BROWSER YOLO-PROCESSED STREAM
# ====================================================================

processed_frame_lock = threading.Lock()
processed_frame_jpeg = None
processed_frame_sequence = 0


def update_processed_frame(frame):
    """Publish the latest YOLO-annotated frame for the browser."""
    global processed_frame_jpeg, processed_frame_sequence

    if frame is None:
        return

    try:
        ok, encoded = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), 85],
        )

        if not ok:
            return

        payload = encoded.tobytes()

        with processed_frame_lock:
            processed_frame_jpeg = payload
            processed_frame_sequence += 1

    except Exception as exc:
        print(f"[DASHBOARD] Processed-frame encode error: {exc}")


# ====================================================================
# MAIN
# ====================================================================

def main():

    global running

    print()
    print("=" * 70)
    print("AI RESCUE ROBOT")
    print("=" * 70)

    print(
        f"Laptop       : {LAPTOP_IP}"
    )

    print(
        f"Camera       : {CAMERA_IP}"
    )

    print(
        f"Arm          : {ARM_IP}:{ARM_PORT}"
    )

    print(
        f"Motor        : {MOTOR_IP}:{MOTOR_PORT}"
    )

    print(
        f"Dashboard    : "
        f"http://{LAPTOP_IP}:{DASHBOARD_PORT}"
    )

    print("=" * 70)

    # ---------------------------------------------------------------
    # CAMERA
    # ---------------------------------------------------------------

    camera = CameraStream(
        CAMERA_STREAM
    )

    # ---------------------------------------------------------------
    # ARM
    # ---------------------------------------------------------------

    global arm

    arm = ArmClient()

    # ---------------------------------------------------------------
    # MOTOR
    # ---------------------------------------------------------------

    global motor

    motor = MotorClient()

    # ---------------------------------------------------------------
    # YOLO
    # ---------------------------------------------------------------

    tracker = HumanTracker()

    # ---------------------------------------------------------------
    # FPS
    # ---------------------------------------------------------------

    fps_counter = FPSCounter()

    # ---------------------------------------------------------------
    # DASHBOARD
    # ---------------------------------------------------------------

    dashboard = start_dashboard()

    # ---------------------------------------------------------------
    # START CONNECTIONS
    # ---------------------------------------------------------------

    camera.start()

    arm.start()

    motor.start()

    # ---------------------------------------------------------------
    # START AI LOOP
    # ---------------------------------------------------------------

    try:

        ai_control_loop(
            tracker,
            camera,
            fps_counter
        )

    except KeyboardInterrupt:

        print(
            "\n[SYSTEM] Keyboard interrupt"
        )

    except Exception as exc:

        print(
            f"\n[SYSTEM] Fatal error: "
            f"{exc}"
        )

    finally:

        print()
        print(
            "[SYSTEM] Shutting down..."
        )

        running = False

        # -----------------------------------------------------------
        # STOP EVERYTHING
        # -----------------------------------------------------------

        try:
            motor.stop_motor(True)
        except Exception:
            pass

        try:
            arm.stop_arm()
        except Exception:
            pass

        try:
            motor.stop()
        except Exception:
            pass

        try:
            arm.stop()
        except Exception:
            pass

        try:
            camera.stop()
        except Exception:
            pass

        try:
            dashboard.shutdown()
        except Exception:
            pass

        cv2.destroyAllWindows()

        print(
            "[SYSTEM] Shutdown complete"
        )


# ====================================================================
# ENTRY POINT
# ====================================================================

if __name__ == "__main__":

    main()