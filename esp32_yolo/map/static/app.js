const wsStatus = document.getElementById('ws-status');
const survivorsList = document.getElementById('survivors-list');
const logContent = document.getElementById('log-content');

let state = null;
let loggedEvents = new Set(); 

// --- LEAFLET MAP INITIALIZATION ---
const BASE_LAT = 34.0183;
const BASE_LON = -118.4915;

const map = L.map('map').setView([BASE_LAT, BASE_LON], 20);

L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    attribution: 'Tiles &copy; Esri',
    maxZoom: 22
}).addTo(map);

function createCustomIcon(color, text, isRobot) {
    const html = isRobot ? 
        `<div style="background-color: ${color}; width: 20px; height: 20px; border-radius: 50%; border: 3px solid white; box-shadow: 0 0 15px ${color}; display: flex; align-items: center; justify-content: center; font-size: 10px;">🤖</div>` :
        `<div style="background-color: ${color}; width: 16px; height: 16px; border-radius: 50%; border: 2px solid white; box-shadow: 0 0 10px ${color};"></div>
         <div style="color: white; font-weight: bold; text-shadow: 1px 1px 2px black; position: absolute; left: 20px; top: 0px; white-space: nowrap;">${text}</div>`;
         
    return L.divIcon({
        className: 'custom-leaflet-marker',
        html: html,
        iconSize: [20, 20],
        iconAnchor: [10, 10]
    });
}

// Map Layers
let robotMarker = null;
let robotPath = L.polyline([], {color: '#0ea5e9', weight: 4, dashArray: '5, 10', opacity: 0.5}).addTo(map);
let plannedPathLine = L.polyline([], {color: '#22c55e', weight: 4}).addTo(map);
let survivorMarkers = {};
let fovPolygon = L.polygon([], {color: 'white', fillColor: '#ffffff', fillOpacity: 0.2, weight: 1}).addTo(map);
let obstacleLayers = [];

function localToLatLng(x, y) {
    const metersPerDegreeLat = 111111;
    const metersPerDegreeLon = 111111 * Math.cos(BASE_LAT * Math.PI / 180);
    const scale = 2.0; 
    const dLat = (y * scale) / metersPerDegreeLat;
    const dLon = (x * scale) / metersPerDegreeLon;
    return [BASE_LAT + dLat, BASE_LON + dLon];
}

// --- LOGGING ---
function addLog(message) {
    const time = new Date().toLocaleTimeString();
    const entryId = `${time}-${message}`;
    if(loggedEvents.has(entryId)) return;
    loggedEvents.add(entryId);
    
    const div = document.createElement('div');
    div.className = 'log-entry';
    div.innerHTML = `<span class="log-time">${time}</span> ${message}`;
    logContent.appendChild(div);
    logContent.scrollTop = logContent.scrollHeight;
}

// --- WEBSOCKET CONNECTION ---
const ws = new WebSocket(`ws://${window.location.host}/ws`);

ws.onopen = () => {
    wsStatus.textContent = 'CONNECTED';
    wsStatus.className = 'text-green';
    addLog("Simulation engine connected.");
};

ws.onclose = () => {
    wsStatus.textContent = 'DISCONNECTED';
    wsStatus.className = 'text-red';
    addLog("Lost connection to simulation engine.");
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'full_state' || data.type === 'update') {
        updateState(data.state);
    }
};

function sendCommand(cmd) {
    if(ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({command: cmd}));
        addLog(`COMMAND ISSUED: ${cmd}`);
    }
}

let lastReplans = 0;

function updateState(newState) {
    if (state && newState.survivors.length > state.survivors.length) {
        const oldIds = new Set(state.survivors.map(s => s.id));
        for (let s of newState.survivors) {
            if (!oldIds.has(s.id)) {
                addLog(`TARGET AQUIRED. Autonomous navigation to ${s.id} initiated.`);
            }
        }
    }
    
    if (state && newState.stats.replans > lastReplans) {
        addLog(`REPLAN EVENT: Path blocked. Recalculating A* route...`);
        lastReplans = newState.stats.replans;
    }

    state = newState;
    
    // Update Telemetry
    document.getElementById('stat-battery').textContent = `${state.stats.battery}%`;
    document.getElementById('battery-indicator').textContent = `BATTERY: ${state.stats.battery}%`;
    if(state.stats.battery < 20) {
        document.getElementById('battery-indicator').style.color = '#ef4444';
        document.getElementById('stat-battery').className = 'text-red';
    }
    
    document.getElementById('stat-dist').textContent = `${state.stats.distance} m`;
    document.getElementById('stat-replans').textContent = state.stats.replans;
    document.getElementById('stat-plan-time').textContent = `${state.stats.planning_time_ms} ms`;
    
    const dur = state.stats.mission_duration;
    const mins = Math.floor(dur / 60);
    const secs = dur % 60;
    document.getElementById('stat-time').textContent = `${mins}m ${secs}s`;
    
    updateSurvivorsPanel();
    updateLeafletMap();
}

function updateSurvivorsPanel() {
    if(!state) return;
    survivorsList.innerHTML = '';
    state.survivors.forEach(s => {
        const div = document.createElement('div');
        div.className = `survivor-card status-${s.status}`;
        let locText = "UNKNOWN";
        if(s.location) {
            const ll = localToLatLng(s.location.x, s.location.y);
            locText = `${ll[0].toFixed(5)}, ${ll[1].toFixed(5)}`;
        }
        div.innerHTML = `
            <strong>${s.id}</strong> (Track: ${s.track_id})<br>
            <span style="font-size: 11px; color: #888;">Status:</span> ${s.status}<br>
            <span style="font-size: 11px; color: #888;">GPS:</span> ${locText}
        `;
        survivorsList.appendChild(div);
    });
}

let movingHazardLayers = [];

function updateLeafletMap() {
    if (!state) return;

    // Robot Marker
    const robotLatLng = localToLatLng(state.robot.x, state.robot.y);
    if (!robotMarker) {
        robotMarker = L.marker(robotLatLng, {icon: createCustomIcon('#0ea5e9', '', true)}).addTo(map);
        map.panTo(robotLatLng);
    } else {
        robotMarker.setLatLng(robotLatLng);
    }

    // Traveled Path
    if(state.robot.trajectory) {
        const latLngs = state.robot.trajectory.map(p => localToLatLng(p.x, p.y));
        latLngs.push(robotLatLng);
        robotPath.setLatLngs(latLngs);
    }
    
    // Planned Path (A*)
    if(state.planned_path) {
        const pLatLngs = state.planned_path.map(p => localToLatLng(p.x, p.y));
        pLatLngs.unshift(robotLatLng); // connect robot to start of planned path
        plannedPathLine.setLatLngs(pLatLngs);
    }

    // FOV Cone
    const fovLength = 15; 
    const headingRad = (90 - state.robot.heading) * Math.PI / 180;
    const halfFov = 30 * Math.PI / 180;
    const fovLeftX = state.robot.x + fovLength * Math.cos(headingRad + halfFov);
    const fovLeftY = state.robot.y + fovLength * Math.sin(headingRad + halfFov);
    const fovRightX = state.robot.x + fovLength * Math.cos(headingRad - halfFov);
    const fovRightY = state.robot.y + fovLength * Math.sin(headingRad - halfFov);
    fovPolygon.setLatLngs([
        robotLatLng,
        localToLatLng(fovLeftX, fovLeftY),
        localToLatLng(fovRightX, fovRightY)
    ]);

    // Static Obstacles
    obstacleLayers.forEach(l => map.removeLayer(l));
    obstacleLayers = [];
    state.obstacles.forEach(obs => {
        const s = obs.size;
        const pts = [
            localToLatLng(obs.x - s, obs.y - s),
            localToLatLng(obs.x + s, obs.y - s),
            localToLatLng(obs.x + s, obs.y + s),
            localToLatLng(obs.x - s, obs.y + s)
        ];
        const p = L.polygon(pts, {color: '#ef4444', fillColor: '#ef4444', fillOpacity: 0.6, weight: 1}).addTo(map);
        obstacleLayers.push(p);
    });

    // Moving Hazards
    movingHazardLayers.forEach(l => map.removeLayer(l));
    movingHazardLayers = [];
    state.moving_obstacles.forEach(h => {
        // Draw the hazard itself as an orange circle
        const c = L.circle(localToLatLng(h.x, h.y), {
            radius: h.radius, // This is roughly in meters on the leaflet map depending on latitude, 
                             // but we can just use the leafet radius which is in meters by default!
            color: '#f97316', // Orange
            fillColor: '#f97316',
            fillOpacity: 0.8
        }).addTo(map);
        movingHazardLayers.push(c);
        
        // Draw predicted trajectory (1 second ahead)
        const predLine = L.polyline([
            localToLatLng(h.x, h.y),
            localToLatLng(h.x + h.vx * 1.0, h.y + h.vy * 1.0)
        ], {color: '#f97316', weight: 2, dashArray: '3, 3'}).addTo(map);
        movingHazardLayers.push(predLine);
    });

    // Survivors
    const activeSurvivorIds = new Set();
    state.survivors.forEach(s => {
        if(!s.location) return;
        activeSurvivorIds.add(s.id);
        const latLng = localToLatLng(s.location.x, s.location.y);
        let color = '#ef4444';
        if(s.status === 'TRACKING') color = '#22c55e';
        if(s.status === 'TEMPORARILY_LOST') color = '#eab308';
        
        if (!survivorMarkers[s.id]) {
            survivorMarkers[s.id] = L.marker(latLng, {icon: createCustomIcon(color, `ID: ${s.id}`, false)}).addTo(map);
        } else {
            survivorMarkers[s.id].setLatLng(latLng);
            survivorMarkers[s.id].setIcon(createCustomIcon(color, `ID: ${s.id}`, false));
        }
    });
    
    for (const id in survivorMarkers) {
        if (!activeSurvivorIds.has(id)) {
            map.removeLayer(survivorMarkers[id]);
            delete survivorMarkers[id];
        }
    }
}

// ==========================================
// --- TAB SWITCHING & FIREBASE LIVE MAP ---
// ==========================================

let currentView = 'local';
let firebaseMap = null;
let fbMarkers = [];
let fbLatestMarker = null;
let latestFirebaseDetection = null;
let fbLoggedEvents = new Set();
let fbPollInterval = null;

function addFbLog(message) {
    const fbLogContent = document.getElementById('fb-log-content');
    if (!fbLogContent) return;
    const time = new Date().toLocaleTimeString();
    const entryId = `${time}-${message}`;
    if (fbLoggedEvents.has(entryId)) return;
    fbLoggedEvents.add(entryId);
    
    const div = document.createElement('div');
    div.className = 'log-entry';
    div.innerHTML = `<span class="log-time">${time}</span> ${message}`;
    fbLogContent.appendChild(div);
    fbLogContent.scrollTop = fbLogContent.scrollHeight;
}

function switchView(viewName) {
    currentView = viewName;
    const viewLocal = document.getElementById('view-local');
    const viewFirebase = document.getElementById('view-firebase');
    const btnLocal = document.getElementById('tab-btn-local');
    const btnFirebase = document.getElementById('tab-btn-firebase');

    if (viewName === 'local') {
        viewLocal.style.display = 'flex';
        viewFirebase.style.display = 'none';
        btnLocal.classList.add('active');
        btnFirebase.classList.remove('active');
        setTimeout(() => {
            map.invalidateSize();
        }, 150);
    } else if (viewName === 'firebase') {
        viewLocal.style.display = 'none';
        viewFirebase.style.display = 'flex';
        btnLocal.classList.remove('active');
        btnFirebase.classList.add('active');
        
        if (!firebaseMap) {
            initFirebaseMap();
        } else {
            setTimeout(() => {
                firebaseMap.invalidateSize();
            }, 150);
        }
        fetchFirebaseCoordinates(true);
    }
}

function initFirebaseMap() {
    const defaultLat = 11.262333;
    const defaultLon = 78.098110;
    
    firebaseMap = L.map('firebase-map').setView([defaultLat, defaultLon], 18);
    
    // Satellite Imagery
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution: 'Tiles &copy; Esri',
        maxZoom: 22
    }).addTo(firebaseMap);

    // Street & Place Labels overlay for high accuracy
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', {
        attribution: 'Labels &copy; Esri',
        maxZoom: 22
    }).addTo(firebaseMap);

    addFbLog("Firebase Satellite Map initialized. Default center: Namakkal Campus (11.262333, 78.098110).");
}

function createLatestBeaconIcon() {
    return L.divIcon({
        className: 'custom-leaflet-marker',
        html: `
            <div class="fb-latest-beacon">
                <div class="fb-latest-ring"></div>
                <div class="fb-latest-dot"></div>
            </div>
            <div style="color: #ef4444; background: rgba(0,0,0,0.8); border: 1px solid #ef4444; border-radius: 3px; padding: 2px 6px; font-weight: bold; font-size: 11px; white-space: nowrap; position: absolute; left: 32px; top: 3px; box-shadow: 0 0 10px rgba(239,68,68,0.5);">
                🚨 LATEST SURVIVOR
            </div>
        `,
        iconSize: [30, 30],
        iconAnchor: [15, 15]
    });
}

function createHistoryMarkerIcon(text) {
    return L.divIcon({
        className: 'custom-leaflet-marker',
        html: `
            <div style="background-color: #0ea5e9; width: 14px; height: 14px; border-radius: 50%; border: 2px solid white; box-shadow: 0 0 8px #0ea5e9;"></div>
            <div style="color: #38bdf8; font-size: 10px; font-weight: bold; text-shadow: 1px 1px 2px black; position: absolute; left: 18px; top: -2px; white-space: nowrap;">${text}</div>
        `,
        iconSize: [16, 16],
        iconAnchor: [8, 8]
    });
}

async function fetchFirebaseCoordinates(isManual = false) {
    const livePill = document.getElementById('fb-live-pill');
    if (livePill) livePill.textContent = '● SYNCING...';

    let rawData = null;
    try {
        // First try server proxy to prevent any CORS restrictions
        const res = await fetch('/api/firebase_coordinates');
        if (res.ok) {
            const json = await res.json();
            if (json.status === 'success') {
                rawData = json.data;
            }
        }
    } catch (err) {
        console.warn('Backend proxy fetch failed, trying direct Firebase fetch...', err);
    }

    // Fallback: Direct Firebase REST API fetch
    if (!rawData) {
        try {
            const directRes = await fetch('https://newsdetection-7d302-default-rtdb.firebaseio.com/.json');
            if (directRes.ok) {
                rawData = await directRes.json();
            }
        } catch (err) {
            console.error('Direct Firebase fetch failed:', err);
            addFbLog(`Error syncing with Firebase: ${err.message}`);
            if (livePill) livePill.textContent = '⚠ SYNC ERROR';
            return;
        }
    }

    if (livePill) livePill.textContent = '● AUTO-SYNC ACTIVE';
    
    // Extract all detection objects containing latitude and longitude
    const detections = [];
    function traverse(obj) {
        if (!obj || typeof obj !== 'object') return;
        if (typeof obj.latitude === 'number' && typeof obj.longitude === 'number') {
            detections.push(obj);
            return;
        }
        for (const key of Object.keys(obj)) {
            traverse(obj[key]);
        }
    }
    traverse(rawData);

    if (detections.length === 0) {
        addFbLog("No coordinate records found in Firebase Realtime Database.");
        return;
    }

    // Sort by timestamp descending (newest first)
    detections.sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0));

    const latest = detections[0];
    const isNewDetection = !latestFirebaseDetection || latest.timestamp !== latestFirebaseDetection.timestamp;
    latestFirebaseDetection = latest;

    // Update Telemetry Panel
    document.getElementById('fb-obj').textContent = (latest.object || latest.class || 'HUMAN').toUpperCase();
    document.getElementById('fb-conf').textContent = latest.confidence ? `${(latest.confidence * 100).toFixed(1)}%` : 'N/A';
    document.getElementById('fb-lat').textContent = latest.latitude.toFixed(6);
    document.getElementById('fb-lon').textContent = latest.longitude.toFixed(6);
    
    const dateStr = latest.timestamp ? new Date(latest.timestamp).toLocaleString() : 'N/A';
    document.getElementById('fb-time').textContent = dateStr;
    document.getElementById('fb-loc-name').textContent = latest.location_name || 'Configured Campus Area';
    document.getElementById('fb-total-count').textContent = `${detections.length} RECORDS`;

    if (isNewDetection || isManual) {
        addFbLog(`Latest Coordinate Synced: Lat ${latest.latitude.toFixed(6)}, Lon ${latest.longitude.toFixed(6)} (${latest.object || 'human'})`);
    }

    // Render Markers on Firebase Map
    if (firebaseMap) {
        // Clear previous markers
        fbMarkers.forEach(m => firebaseMap.removeLayer(m));
        fbMarkers = [];
        if (fbLatestMarker) {
            firebaseMap.removeLayer(fbLatestMarker);
            fbLatestMarker = null;
        }

        // Render historical markers (skip the 0th item which is the latest)
        for (let i = 1; i < detections.length; i++) {
            const item = detections[i];
            const timeStr = item.timestamp ? new Date(item.timestamp).toLocaleTimeString() : '';
            const m = L.marker([item.latitude, item.longitude], {
                icon: createHistoryMarkerIcon(timeStr)
            }).addTo(firebaseMap);
            
            m.bindPopup(`
                <div style="font-family: monospace; font-size: 12px;">
                    <strong style="color: #0ea5e9;">DETECTION ID:</strong> ${(item.detection_id || '').substring(0, 8)}...<br>
                    <strong>Object:</strong> ${item.object || item.class || 'human'}<br>
                    <strong>Confidence:</strong> ${(item.confidence * 100).toFixed(1)}%<br>
                    <strong>Time:</strong> ${dateStr}<br>
                    <strong>GPS:</strong> ${item.latitude.toFixed(6)}, ${item.longitude.toFixed(6)}
                </div>
            `);
            fbMarkers.push(m);
        }

        // Render LATEST marker with prominent pulsating beacon
        fbLatestMarker = L.marker([latest.latitude, latest.longitude], {
            icon: createLatestBeaconIcon(),
            zIndexOffset: 1000
        }).addTo(firebaseMap);

        fbLatestMarker.bindPopup(`
            <div style="font-family: monospace; font-size: 13px;">
                <div style="color: #ef4444; font-weight: bold; font-size: 14px; margin-bottom: 4px;">🚨 LATEST DETECTED SURVIVOR</div>
                <strong>Object:</strong> ${(latest.object || latest.class || 'human').toUpperCase()}<br>
                <strong>Confidence:</strong> ${(latest.confidence * 100).toFixed(1)}%<br>
                <strong>GPS:</strong> ${latest.latitude.toFixed(6)}, ${latest.longitude.toFixed(6)}<br>
                <strong>Timestamp:</strong> ${dateStr}<br>
                <div style="color: #888; font-size: 11px; margin-top: 4px;">${latest.location_name || ''}</div>
            </div>
        `);

        // Center on latest if view is active or manual refresh
        if (isManual || isNewDetection) {
            firebaseMap.flyTo([latest.latitude, latest.longitude], 18, {
                duration: 1.2
            });
            setTimeout(() => {
                if (fbLatestMarker) fbLatestMarker.openPopup();
            }, 1200);
        }
    }

    // Populate Detections History List
    const listContainer = document.getElementById('fb-detections-list');
    if (listContainer) {
        listContainer.innerHTML = '';
        detections.forEach((det, idx) => {
            const card = document.createElement('div');
            card.className = `survivor-card ${idx === 0 ? 'status-TRACKING' : ''}`;
            card.style.cursor = 'pointer';
            
            const itemTime = det.timestamp ? new Date(det.timestamp).toLocaleTimeString() : 'N/A';
            const shortId = (det.detection_id || `REC-${idx}`).substring(0, 10);
            
            card.innerHTML = `
                <div style="display: flex; justify-content: space-between;">
                    <strong style="color: ${idx === 0 ? '#ef4444' : '#38bdf8'};">${idx === 0 ? '★ LATEST: ' : ''}${shortId}</strong>
                    <span style="font-size: 11px; color: #94a3b8;">${itemTime}</span>
                </div>
                <div style="font-size: 12px; color: #cbd5e1; margin-top: 3px;">
                    Target: ${det.object || det.class || 'human'} (${(det.confidence * 100).toFixed(0)}%)
                </div>
                <div style="font-size: 11px; color: #64748b;">
                    GPS: ${det.latitude.toFixed(5)}, ${det.longitude.toFixed(5)}
                </div>
            `;
            
            card.onclick = () => {
                if (firebaseMap) {
                    firebaseMap.flyTo([det.latitude, det.longitude], 19, { duration: 1.0 });
                    if (idx === 0 && fbLatestMarker) {
                        fbLatestMarker.openPopup();
                    } else if (fbMarkers[idx - 1]) {
                        fbMarkers[idx - 1].openPopup();
                    }
                }
            };
            
            listContainer.appendChild(card);
        });
    }
}

function centerOnLatestFirebase() {
    if (firebaseMap && latestFirebaseDetection) {
        firebaseMap.flyTo([latestFirebaseDetection.latitude, latestFirebaseDetection.longitude], 19, {
            duration: 1.0
        });
        if (fbLatestMarker) {
            setTimeout(() => fbLatestMarker.openPopup(), 1000);
        }
        addFbLog("Map centered on latest Firebase coordinate.");
    } else {
        fetchFirebaseCoordinates(true);
    }
}

// Background auto-sync interval for Firebase (every 8 seconds)
fbPollInterval = setInterval(() => {
    fetchFirebaseCoordinates(false);
}, 8000);

// Initial silent fetch so data is immediately cached
fetchFirebaseCoordinates(false);

