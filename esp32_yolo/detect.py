import cv2
import numpy as np
import requests
import threading
import time
import os
from datetime import datetime
from ultralytics import YOLO


# ============================================================
# ESP32-CAM CONFIGURATION
# ============================================================

ESP32_IP = "172.17.98.207"
STREAM_URL = f"http://{ESP32_IP}/stream"


# ============================================================
# YOLO CONFIGURATION
# ============================================================

# Pose model:
# Detects person + body keypoints.
POSE_MODEL_PATH = "yolo26m-pose.pt"

# Face model:
# We use a small YOLO detector for independent face detection.
#
# IMPORTANT:
# This file must exist in the project folder.
# You can replace it with your own trained face model later.
FACE_MODEL_PATH = "yolo26n.pt"

# COCO person class
PERSON_CLASS_ID = 0

# Confidence thresholds
POSE_CONFIDENCE = 0.30
FACE_CONFIDENCE = 0.30

# Larger = potentially better accuracy, more processing
POSE_IMAGE_SIZE = 640
FACE_IMAGE_SIZE = 640


# ============================================================
# STREAM CONFIGURATION
# ============================================================

HTTP_CONNECT_TIMEOUT = 5
HTTP_READ_TIMEOUT = 10

MAX_JPEG_SIZE = 2_000_000


# ============================================================
# DETECTION IMAGE SAVING
# ============================================================

SAVE_DETECTIONS = True

DETECTION_DIRECTORY = "detections"

# Minimum time between saved detection images
SAVE_COOLDOWN = 3.0


# ============================================================
# GLOBAL STREAM STATE
# ============================================================

latest_frame = None

frame_lock = threading.Lock()

stream_running = True
stream_connected = False

stream_error = None

frames_received = 0

last_frame_time = 0.0


# ============================================================
# LATEST FRAME BUFFER
# ============================================================

def set_latest_frame(frame):
    global latest_frame
    global frames_received
    global last_frame_time

    with frame_lock:
        latest_frame = frame

    frames_received += 1
    last_frame_time = time.time()


def get_latest_frame():

    with frame_lock:

        if latest_frame is None:
            return None

        return latest_frame.copy()


# ============================================================
# ESP32 MJPEG STREAM READER
# ============================================================

class ESP32StreamReader(threading.Thread):

    def __init__(self, url):

        super().__init__(daemon=True)

        self.url = url

        self.running = True

        self.session = requests.Session()

        self.connection = None

        self.frames_received = 0

        self.bytes_received = 0

    def stop(self):

        self.running = False

        try:

            if self.connection is not None:
                self.connection.close()

        except Exception:
            pass

        try:
            self.session.close()

        except Exception:
            pass

    def run(self):

        global stream_connected
        global stream_error

        print()
        print("======================================")
        print(" ESP32-CAM STREAM READER")
        print("======================================")
        print(f"URL: {self.url}")
        print()

        while self.running:

            try:

                print("Connecting to ESP32-CAM...")

                self.connection = self.session.get(
                    self.url,
                    stream=True,
                    timeout=(
                        HTTP_CONNECT_TIMEOUT,
                        HTTP_READ_TIMEOUT
                    ),
                    headers={
                        "User-Agent": "ESP32-Rescue-Vision/1.0",
                        "Accept": "*/*",
                        "Connection": "keep-alive"
                    }
                )

                print(
                    f"HTTP Status: "
                    f"{self.connection.status_code}"
                )

                content_type = self.connection.headers.get(
                    "Content-Type",
                    "unknown"
                )

                print(
                    f"Content-Type: {content_type}"
                )

                if self.connection.status_code != 200:

                    raise RuntimeError(
                        f"ESP32 returned HTTP "
                        f"{self.connection.status_code}"
                    )

                stream_connected = True
                stream_error = None

                print()
                print("ESP32 stream connected.")
                print("Waiting for JPEG frames...")
                print()

                self.read_mjpeg_stream()

            except requests.exceptions.ConnectTimeout:

                stream_connected = False
                stream_error = "Connection timeout"

                print(
                    "[ERROR] ESP32 connection timeout."
                )

            except requests.exceptions.ReadTimeout:

                stream_connected = False
                stream_error = "Read timeout"

                print(
                    "[ERROR] ESP32 stream read timeout."
                )

            except requests.exceptions.ConnectionError as e:

                stream_connected = False
                stream_error = "Connection error"

                print(
                    "[ERROR] Connection error:",
                    e
                )

            except Exception as e:

                stream_connected = False
                stream_error = str(e)

                print(
                    "[ERROR] Stream error:",
                    repr(e)
                )

            finally:

                stream_connected = False

                try:

                    if self.connection is not None:
                        self.connection.close()

                except Exception:
                    pass

                self.connection = None

            if self.running:

                print(
                    "Reconnecting in 2 seconds..."
                )

                time.sleep(2)

    # --------------------------------------------------------
    # MJPEG PARSER
    # --------------------------------------------------------

    def read_mjpeg_stream(self):

        buffer = bytearray()

        JPEG_START = b"\xff\xd8"
        JPEG_END = b"\xff\xd9"

        for chunk in self.connection.iter_content(
            chunk_size=4096
        ):

            if not self.running:
                return

            if not chunk:
                continue

            buffer.extend(chunk)

            self.bytes_received += len(chunk)

            # ------------------------------------------------
            # Find JPEG START
            # ------------------------------------------------

            start = buffer.find(JPEG_START)

            if start == -1:

                if len(buffer) > MAX_JPEG_SIZE:
                    buffer.clear()

                continue

            # Remove HTTP/MJPEG data before JPEG
            if start > 0:

                del buffer[:start]

            # ------------------------------------------------
            # Find JPEG END
            # ------------------------------------------------

            end = buffer.find(
                JPEG_END,
                len(JPEG_START)
            )

            if end == -1:

                if len(buffer) > MAX_JPEG_SIZE:

                    print(
                        "[WARNING] Invalid JPEG buffer."
                    )

                    buffer.clear()

                continue

            # Include JPEG END bytes
            jpeg_data = bytes(
                buffer[:end + len(JPEG_END)]
            )

            # Remove processed JPEG
            del buffer[
                :end + len(JPEG_END)
            ]

            # ------------------------------------------------
            # Decode JPEG
            # ------------------------------------------------

            np_data = np.frombuffer(
                jpeg_data,
                dtype=np.uint8
            )

            frame = cv2.imdecode(
                np_data,
                cv2.IMREAD_COLOR
            )

            if frame is None:

                print(
                    "[WARNING] JPEG decode failed."
                )

                continue

            self.frames_received += 1

            set_latest_frame(frame)


# ============================================================
# MODEL LOADING
# ============================================================

def load_models():

    print()
    print("======================================")
    print(" LOADING AI MODELS")
    print("======================================")
    print()

    print(
        f"Loading pose model: "
        f"{POSE_MODEL_PATH}"
    )

    pose_model = YOLO(
        POSE_MODEL_PATH
    )

    print(
        "Pose model loaded."
    )

    print()

    print(
        f"Loading face model: "
        f"{FACE_MODEL_PATH}"
    )

    face_model = YOLO(
        FACE_MODEL_PATH
    )

    print(
        "Face model loaded."
    )

    return pose_model, face_model


# ============================================================
# DEVICE SELECTION
# ============================================================

def get_device():

    try:

        import torch

        if torch.cuda.is_available():

            gpu_name = torch.cuda.get_device_name(0)

            print()
            print("======================================")
            print(" GPU DETECTED")
            print("======================================")
            print(gpu_name)
            print()

            return 0

    except Exception as e:

        print(
            "Could not check CUDA:",
            e
        )

    print()
    print("CUDA GPU not available.")
    print("Using CPU.")
    print()

    return "cpu"


# ============================================================
# DRAW TEXT
# ============================================================

def draw_text(
    frame,
    text,
    position,
    scale=0.65,
    thickness=2
):

    cv2.putText(
        frame,
        text,
        position,
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        (0, 255, 0),
        thickness,
        cv2.LINE_AA
    )


# ============================================================
# BODY KEYPOINT NAMES
# ============================================================

KEYPOINT_NAMES = [

    "nose",

    "left_eye",
    "right_eye",

    "left_ear",
    "right_ear",

    "left_shoulder",
    "right_shoulder",

    "left_elbow",
    "right_elbow",

    "left_wrist",
    "right_wrist",

    "left_hip",
    "right_hip",

    "left_knee",
    "right_knee",

    "left_ankle",
    "right_ankle"
]


# ============================================================
# SKELETON CONNECTIONS
# ============================================================

SKELETON = [

    # Face
    (0, 1),
    (0, 2),
    (1, 3),
    (2, 4),

    # Left arm
    (5, 7),
    (7, 9),

    # Right arm
    (6, 8),
    (8, 10),

    # Shoulders
    (5, 6),

    # Torso
    (5, 11),
    (6, 12),
    (11, 12),

    # Left leg
    (11, 13),
    (13, 15),

    # Right leg
    (12, 14),
    (14, 16)
]


# ============================================================
# DRAW BODY POSE
# ============================================================

def draw_pose(
    frame,
    keypoints,
    confidence_threshold=0.25
):

    visible_keypoints = []

    points = []

    for i in range(len(KEYPOINT_NAMES)):

        x, y = keypoints[i][:2]

        if len(keypoints[i]) >= 3:
            confidence = keypoints[i][2]
        else:
            confidence = 1.0

        if confidence >= confidence_threshold:

            x = int(x)
            y = int(y)

            points.append(
                (x, y)
            )

            visible_keypoints.append(
                KEYPOINT_NAMES[i]
            )

            cv2.circle(
                frame,
                (x, y),
                5,
                (0, 255, 255),
                -1
            )

        else:

            points.append(None)

    # Draw skeleton
    for a, b in SKELETON:

        if (
            a < len(points)
            and b < len(points)
            and points[a] is not None
            and points[b] is not None
        ):

            cv2.line(
                frame,
                points[a],
                points[b],
                (255, 255, 0),
                2
            )

    return visible_keypoints


# ============================================================
# FACE DETECTION
# ============================================================

def detect_faces(
    frame,
    face_model,
    device
):

    results = face_model.predict(
        source=frame,
        conf=FACE_CONFIDENCE,
        imgsz=FACE_IMAGE_SIZE,
        device=device,
        verbose=False
    )

    result = results[0]

    faces = []

    if result.boxes is None:
        return faces

    for box in result.boxes:

        confidence = float(
            box.conf[0]
        )

        x1, y1, x2, y2 = (
            box.xyxy[0]
            .cpu()
            .numpy()
            .astype(int)
        )

        faces.append(
            {
                "box": (
                    x1,
                    y1,
                    x2,
                    y2
                ),
                "confidence": confidence
            }
        )

        # Face rectangle
        cv2.rectangle(
            frame,
            (x1, y1),
            (x2, y2),
            (255, 0, 255),
            2
        )

        cv2.putText(
            frame,
            f"FACE {confidence * 100:.1f}%",
            (x1, max(25, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 0, 255),
            2,
            cv2.LINE_AA
        )

    return faces


# ============================================================
# BODY / PERSON DETECTION
# ============================================================

def detect_body(
    frame,
    pose_model,
    device
):

    results = pose_model.predict(
        source=frame,
        conf=POSE_CONFIDENCE,
        imgsz=POSE_IMAGE_SIZE,
        device=device,
        verbose=False
    )

    result = results[0]

    persons = []

    if result.boxes is None:
        return persons

    if result.keypoints is None:
        return persons

    boxes = result.boxes

    keypoints = result.keypoints

    for i in range(len(boxes)):

        class_id = int(
            boxes.cls[i]
        )

        # Only person
        if class_id != PERSON_CLASS_ID:
            continue

        confidence = float(
            boxes.conf[i]
        )

        x1, y1, x2, y2 = (
            boxes.xyxy[i]
            .cpu()
            .numpy()
            .astype(int)
        )

        # Get keypoints
        kp = keypoints.xy[i].cpu().numpy()

        if keypoints.conf is not None:

            kp_conf = (
                keypoints.conf[i]
                .cpu()
                .numpy()
            )

            kp_combined = np.column_stack(
                (kp, kp_conf)
            )

        else:

            kp_combined = kp

        visible = draw_pose(
            frame,
            kp_combined,
            confidence_threshold=0.25
        )

        # Draw person bounding box
        cv2.rectangle(
            frame,
            (x1, y1),
            (x2, y2),
            (0, 255, 0),
            2
        )

        cv2.putText(
            frame,
            f"PERSON {confidence * 100:.1f}%",
            (x1, max(25, y1 - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.60,
            (0, 255, 0),
            2,
            cv2.LINE_AA
        )

        persons.append(
            {
                "box": (
                    x1,
                    y1,
                    x2,
                    y2
                ),
                "confidence": confidence,
                "visible_keypoints": visible
            }
        )

    return persons


# ============================================================
# SAVE DETECTION
# ============================================================

last_saved_time = 0.0


def save_detection(frame):

    global last_saved_time

    if not SAVE_DETECTIONS:
        return

    now = time.time()

    if (
        now - last_saved_time
        < SAVE_COOLDOWN
    ):
        return

    os.makedirs(
        DETECTION_DIRECTORY,
        exist_ok=True
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S_%f"
    )[:-3]

    filename = (
        f"rescue_detection_{timestamp}.jpg"
    )

    path = os.path.join(
        DETECTION_DIRECTORY,
        filename
    )

    if cv2.imwrite(
        path,
        frame
    ):

        print(
            f"[RESCUE] Detection saved: "
            f"{path}"
        )

        last_saved_time = now


# ============================================================
# CLASSIFY VISIBLE BODY PARTS
# ============================================================

def body_status(person):

    visible = set(
        person["visible_keypoints"]
    )

    def has(*names):

        return any(
            name in visible
            for name in names
        )

    status = {
        "head": has(
            "nose",
            "left_eye",
            "right_eye",
            "left_ear",
            "right_ear"
        ),

        "left_arm": has(
            "left_shoulder",
            "left_elbow",
            "left_wrist"
        ),

        "right_arm": has(
            "right_shoulder",
            "right_elbow",
            "right_wrist"
        ),

        "left_hand": (
            "left_wrist" in visible
        ),

        "right_hand": (
            "right_wrist" in visible
        ),

        "left_leg": has(
            "left_hip",
            "left_knee",
            "left_ankle"
        ),

        "right_leg": has(
            "right_hip",
            "right_knee",
            "right_ankle"
        ),

        "torso": has(
            "left_shoulder",
            "right_shoulder",
            "left_hip",
            "right_hip"
        )
    }

    return status


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("======================================")
    print(" ESP32-CAM RESCUE VISION")
    print("======================================")
    print()
    print("Features:")
    print("  - Person detection")
    print("  - Human pose")
    print("  - Head detection")
    print("  - Hand/wrist visibility")
    print("  - Arm visibility")
    print("  - Leg visibility")
    print("  - Face detection")
    print("  - Detection frame saving")
    print()
    print("Press Q to quit.")
    print()

    # --------------------------------------------------------
    # Load models
    # --------------------------------------------------------

    pose_model, face_model = load_models()

    # --------------------------------------------------------
    # Select GPU/CPU
    # --------------------------------------------------------

    device = get_device()

    # --------------------------------------------------------
    # Start ESP32 stream
    # --------------------------------------------------------

    reader = ESP32StreamReader(
        STREAM_URL
    )

    reader.start()

    print(
        "Waiting for ESP32-CAM frames..."
    )

    # --------------------------------------------------------
    # Wait for first frame
    # --------------------------------------------------------

    start_wait = time.time()

    while (
        latest_frame is None
        and time.time() - start_wait < 15
    ):

        time.sleep(0.1)

    if latest_frame is None:

        print()
        print("======================================")
        print(" NO CAMERA FRAMES")
        print("======================================")
        print()
        print(
            "The ESP32 is reachable on port 80, "
            "but /stream is not providing JPEG frames."
        )
        print()
        print(
            "Fix the ESP32 /stream endpoint first."
        )

        reader.stop()

        return

    print()
    print(
        "First camera frame received."
    )

    print(
        "Starting rescue detection..."
    )

    print()

    # --------------------------------------------------------
    # FPS
    # --------------------------------------------------------

    fps_counter = 0

    fps_start = time.perf_counter()

    display_fps = 0.0

    # --------------------------------------------------------
    # Main loop
    # --------------------------------------------------------

    while True:

        frame = get_latest_frame()

        if frame is None:

            time.sleep(0.01)

            continue

        # Make sure we don't modify the original
        display = frame.copy()

        total_start = time.perf_counter()

        # ----------------------------------------------------
        # BODY / POSE
        # ----------------------------------------------------

        pose_start = time.perf_counter()

        persons = detect_body(
            display,
            pose_model,
            device
        )

        pose_time = (
            time.perf_counter()
            - pose_start
        ) * 1000.0

        # ----------------------------------------------------
        # FACE DETECTION
        # ----------------------------------------------------

        face_start = time.perf_counter()

        faces = detect_faces(
            display,
            face_model,
            device
        )

        face_time = (
            time.perf_counter()
            - face_start
        ) * 1000.0

        # ----------------------------------------------------
        # RESCUE STATUS
        # ----------------------------------------------------

        person_detected = (
            len(persons) > 0
        )

        face_detected = (
            len(faces) > 0
        )

        # ----------------------------------------------------
        # Body status
        # ----------------------------------------------------

        if person_detected:

            person_status = body_status(
                persons[0]
            )

        else:

            person_status = {}

        # ----------------------------------------------------
        # Main status
        # ----------------------------------------------------

        if person_detected:

            highest_person_conf = max(
                p["confidence"]
                for p in persons
            )

            status = (
                f"PERSON DETECTED "
                f"{highest_person_conf * 100:.1f}%"
            )

        elif face_detected:

            status = (
                f"FACE DETECTED "
                f"{len(faces)}"
            )

        else:

            status = (
                "NO HUMAN DETECTED"
            )

        # ----------------------------------------------------
        # UI
        # ----------------------------------------------------

        draw_text(
            display,
            status,
            (10, 30),
            scale=0.75,
            thickness=2
        )

        draw_text(
            display,
            f"Persons: {len(persons)}",
            (10, 58),
            scale=0.55,
            thickness=2
        )

        draw_text(
            display,
            f"Faces: {len(faces)}",
            (10, 82),
            scale=0.55,
            thickness=2
        )

        draw_text(
            display,
            f"Pose: {pose_time:.1f} ms",
            (10, 106),
            scale=0.55,
            thickness=2
        )

        draw_text(
            display,
            f"Face: {face_time:.1f} ms",
            (10, 130),
            scale=0.55,
            thickness=2
        )

        # ----------------------------------------------------
        # Body-part visibility
        # ----------------------------------------------------

        y = 160

        if person_detected:

            visible_parts = []

            if person_status.get("head"):
                visible_parts.append("HEAD")

            if person_status.get("torso"):
                visible_parts.append("TORSO")

            if person_status.get("left_arm"):
                visible_parts.append("L-ARM")

            if person_status.get("right_arm"):
                visible_parts.append("R-ARM")

            if person_status.get("left_hand"):
                visible_parts.append("L-HAND")

            if person_status.get("right_hand"):
                visible_parts.append("R-HAND")

            if person_status.get("left_leg"):
                visible_parts.append("L-LEG")

            if person_status.get("right_leg"):
                visible_parts.append("R-LEG")

            draw_text(
                display,
                "VISIBLE: "
                + (
                    ", ".join(visible_parts)
                    if visible_parts
                    else "NONE"
                ),
                (10, y),
                scale=0.50,
                thickness=2
            )

        # ----------------------------------------------------
        # Connection
        # ----------------------------------------------------

        if stream_connected:

            connection_text = (
                "ESP32: CONNECTED"
            )

        else:

            connection_text = (
                "ESP32: RECONNECTING"
            )

        draw_text(
            display,
            connection_text,
            (10, y + 28),
            scale=0.50,
            thickness=2
        )

        # ----------------------------------------------------
        # FPS
        # ----------------------------------------------------

        fps_counter += 1

        elapsed = (
            time.perf_counter()
            - fps_start
        )

        if elapsed >= 1.0:

            display_fps = (
                fps_counter / elapsed
            )

            fps_counter = 0

            fps_start = time.perf_counter()

        draw_text(
            display,
            f"FPS: {display_fps:.1f}",
            (10, y + 56),
            scale=0.50,
            thickness=2
        )

        # ----------------------------------------------------
        # Save rescue detection
        # ----------------------------------------------------

        if (
            person_detected
            or face_detected
        ):

            save_detection(
                display
            )

        # ----------------------------------------------------
        # Display
        # ----------------------------------------------------

        cv2.imshow(
            "ESP32-CAM RESCUE VISION",
            display
        )

        # ----------------------------------------------------
        # Keyboard
        # ----------------------------------------------------

        key = (
            cv2.waitKey(1)
            & 0xFF
        )

        if key == ord("q"):

            break

    # --------------------------------------------------------
    # Cleanup
    # --------------------------------------------------------

    reader.stop()

    cv2.destroyAllWindows()

    print()
    print(
        "Rescue vision stopped."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print()
        print(
            "Stopped by user."
        )

        cv2.destroyAllWindows()

    except Exception as e:

        print()
        print("======================================")
        print(" FATAL ERROR")
        print("======================================")
        print()
        print(e)

        cv2.destroyAllWindows()