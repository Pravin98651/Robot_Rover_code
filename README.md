# Robot_Rover_code

## Disaster Watch & Robot Telemetry Dashboard

This repository contains a full-stack disaster awareness and autonomous robot monitoring system. It automatically ingests natural disaster data (NASA FIRMS wildfires, USGS earthquakes) and scrapes local news for structural collapse incidents, plotting everything onto a live dashboard. It also features a real-time Live Tracker that maps coordinates of human detections sent from an autonomous rover via Firebase RTDB.

### Project Structure

- `/backend` - A Node.js background worker that ingests feeds, uses Gemini AI for NLP extraction of news articles, geocodes locations, and saves everything to Firestore.
- `/frontend` - A React + Vite frontend using Tailwind CSS and Leaflet maps to visualize disasters and track the rover in real-time.

### Setup Instructions

#### Backend
1. `cd backend`
2. `npm install`
3. Add your `.env` (Gemini & NASA API keys) and `serviceAccountKey.json` (Firebase).
4. `node src/index.js`

#### Frontend
1. `cd frontend`
2. `npm install`
3. `npm run dev`
