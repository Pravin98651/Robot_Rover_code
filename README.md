# Robot_Rover_code

## 🚨 Disaster Watch, Autonomous Rover & Search-and-Rescue (SAR) System

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Node.js](https://img.shields.io/badge/Node.js-18%2B-green.svg)](https://nodejs.org/)
[![React](https://img.shields.io/badge/Frontend-React%20%7C%20Vite%20%7C%20Tailwind-cyan.svg)](https://reactjs.org/)
[![ESP32](https://img.shields.io/badge/Hardware-ESP32%20%7C%20ESP32--CAM-red.svg)](https://www.espressif.com/)
[![YOLOv8](https://img.shields.io/badge/Vision-Ultralytics%20YOLO-brightgreen.svg)](https://ultralytics.com/)
[![Firebase](https://img.shields.io/badge/Cloud-Firebase%20RTDB%20%7C%20Firestore-orange.svg)](https://firebase.google.com/)

An end-to-end intelligent disaster response and autonomous search-and-rescue platform. The system ingests global disaster data (NASA FIRMS, USGS Earthquakes, Gemini-powered news incident extraction), provides real-time situational awareness dashboards, performs edge AI human detection via an ESP32-CAM, guides a physical 5-DOF robotic arm, runs autonomous A* path planning with predictive obstacle avoidance, and synchronizes live survivor coordinates across Cloud and Local Command Centers.

---

## 📂 Project Structure

```text
Robot_Rover_code/
├── backend/                             # Disaster Ingestion & NLP Processing Service
│   ├── src/                            # Node.js worker ingesting NASA FIRMS, USGS, News
│   ├── package.json                    # Backend dependencies
│   └── ...                             # Gemini AI extraction & Firestore storage
│
├── frontend/                            # Global Disaster Monitoring & Telemetry Dashboard
│   ├── src/                            # React + Vite + Tailwind CSS + Leaflet maps
│   ├── package.json                    # Frontend dependencies
│   └── ...                             # Real-time disaster mapping & rover tracking UI
│
├── esp32_yolo/                          # Python Edge AI Vision & Tactical Command Center
│   ├── ai_arm_controller.py            # Core YOLO human detection & robotic arm tracking
│   ├── resq_integration.py             # Zero-modification hook & UDP telemetry proxy
│   ├── map/                            # Autonomous Command Center & Path Simulation
│   │   ├── server.py                   # FastAPI WebSocket, MJPEG stream, & Firebase proxy
│   │   ├── tracker.py                  # Simulation engine & battery energy model
│   │   ├── planner.py                  # A* grid-based pathfinding & obstacle replanning
│   │   ├── logger.py                   # Mission telemetry and detection event recorder
│   │   └── static/                     # Web Command Center Dashboard UI
│   │       ├── index.html              # Multi-tab Command Center Dashboard
│   │       ├── app.js                  # Leaflet maps, simulator engine, & Firebase sync
│   │       └── style.css               # Tactical sci-fi dark-mode interface
│   ├── detect.py                       # Standalone YOLO detection utility
│   └── *.pt                            # YOLO detection and pose estimation weights
│
└── sketch_sep3a/                        # ESP32 Firmware & Hardware Controller
    └── sketch_sep3a.ino                # ESP32-CAM MJPEG server & 5-DOF servo arm controller
```

---

## 🏗️ System Architecture

```text
+-----------------------------------------------------------------------------------+
|                            GLOBAL SATELLITE & DISASTER INTELLIGENCE               |
|  NASA FIRMS (Wildfires) + USGS (Earthquakes) + News Incident Scraper (Gemini AI)  |
+------------------------------------------+----------------------------------------+
                                           |
                                           v
                        +----------------------------------+
                        |         Node.js Backend          |
                        |      (Firestore DB Storage)      |
                        +------------------+---------------+
                                           |
                                           v
                        +----------------------------------+
                        |      React + Vite Frontend       |
                        |    (Global Disaster Dashboard)   |
                        +----------------------------------+

=====================================================================================

+-----------------------------------------------------------------------------------+
|                         LOCAL EDGE SEARCH & RESCUE ROVER                          |
+-----------------------------------------------------------------------------------+
       AI-Thinker ESP32-CAM (MJPEG Stream)
                   |
                   v
       Ultralytics YOLO Human Detection (Python)
         /                                    \
 (TCP JSON Coords)                   (Zero-Mod Hook / UDP)
       v                                        v
 ESP32 5-DOF Arm Controller               FastAPI / WebSockets Command Center
 (Physical Servo Tracking)                - A* Path Planning & Dynamic Avoidance
                                          - Moving Hazard Predictive Rerouting
                                          - Battery & Energy Telemetry
                                          - Real-time Satellite Rescue Map
                                          - Firebase RTDB Cloud Sync
```

---

## 🚀 Modules Breakdown & Setup

### 1. Backend (`/backend`)
A Node.js service that automatically fetches natural disaster events and scrapes news feeds, analyzing unstructured text with Google Gemini AI to extract event categories, severities, and geolocations before saving them to Firebase Firestore.
```bash
cd backend
npm install
# Configure .env with GEMINI_API_KEY, NASA_API_KEY and serviceAccountKey.json
node src/index.js
```

### 2. Frontend Dashboard (`/frontend`)
A modern React application built with Vite and Tailwind CSS. It visualizes worldwide disaster incidents on Leaflet maps and tracks incoming rover coordinates from Firebase Realtime Database.
```bash
cd frontend
npm install
npm run dev
```

### 3. Edge AI Vision & Command Center (`/esp32_yolo`)
Runs edge AI vision on live camera streams from the ESP32-CAM, tracks human survivors, commands physical servo kinematics, and serves the multi-tab Command Center web application:
- **Tab 1: Local Mission**: Embedded video stream with YOLO bounding boxes, local A* path planning simulation with dynamic roadblocks and moving hazards, battery telemetry, and mission logs.
- **Tab 2: Firebase Live GPS Map**: Cloud integration syncing with Firebase Realtime Database (`https://newsdetection-7d302-default-rtdb.firebaseio.com/`), identifying latest survivors with an animated pulsing radar beacon.

```powershell
cd esp32_yolo
python -m venv .venv
.\.venv\Scripts\activate
pip install ultralytics opencv-python fastapi uvicorn websockets numpy
python resq_integration.py
```
Open **`http://localhost:8000`** in your browser.

### 4. ESP32 Hardware Firmware (`/sketch_sep3a`)
Arduino C++ firmware for the AI-Thinker ESP32-CAM and ESP32 robot arm controller:
- Streams MJPEG frames over Wi-Fi (`:81/stream`).
- Listens on TCP port `5000` for normalized target coordinates `{"x": ..., "y": ...}`.
- Controls 5-DOF / 6-DOF servo angles with smooth PID kinematics.

**Flashing Instructions:**
1. Open `sketch_sep3a/sketch_sep3a.ino` in Arduino IDE.
2. Update Wi-Fi SSID and Password:
   ```cpp
   const char* ssid = "YOUR_WIFI_SSID";
   const char* password = "YOUR_WIFI_PASSWORD";
   ```
3. Select board **AI Thinker ESP32-CAM** and upload.

---

## 🎮 Command Center Key Controls

| Control | Action |
| :--- | :--- |
| **`🛰️ LOCAL MISSION` Tab** | Real-time rover path planning simulation and live ESP32-CAM video feed. |
| **`📍 FIREBASE LIVE GPS MAP` Tab** | Cloud-synced global map tracking remote survivor detections. |
| **`⚠ BLOCK CURRENT PATH`** | Spawns an obstacle right in front of the robot to force an immediate A* replan. |
| **`☄ SPAWN STATIC DEBRIS`** | Drops debris on the field to test navigation in rubble. |
| **`🏃 SPAWN MOVING HAZARD`** | Spawns dynamic moving obstacles to demonstrate predictive collision avoidance. |
| **`🔄 REFRESH NOW`** | Force-syncs latest records from Firebase Realtime Database. |
| **`🎯 CENTER LATEST`** | Flies the camera directly to the latest detected survivor coordinates. |

---

## 📜 License
This project is licensed under the MIT License.
