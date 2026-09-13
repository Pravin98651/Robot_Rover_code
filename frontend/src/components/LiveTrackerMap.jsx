import React, { useEffect, useState } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';

// Create a custom icon for the human detection
const personIcon = new L.Icon({
  iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41]
});

// Helper component to smoothly center map when coordinates change
function MapUpdater({ center }) {
  const map = useMap();
  useEffect(() => {
    if (center) {
      map.setView(center, 16, { animate: true });
    }
  }, [center, map]);
  return null;
}

const LiveTrackerMap = () => {
  const [latestDetection, setLatestDetection] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchLatestCoordinate = async () => {
      try {
        const response = await fetch('https://newsdetection-7d302-default-rtdb.firebaseio.com/safetyMonitor/current.json');
        if (!response.ok) throw new Error('Failed to fetch data');
        
        const data = await response.json();
        
        if (data) {
          // Convert the object into an array of its values
          const detections = Object.values(data);
          
          if (detections.length > 0) {
            // Sort descending by timestamp
            detections.sort((a, b) => b.timestamp - a.timestamp);
            
            // Get the absolute latest one
            setLatestDetection(detections[0]);
          }
        }
        setError(null);
      } catch (err) {
        console.error(err);
        setError("Unable to load live coordinates.");
      } finally {
        setLoading(false);
      }
    };

    fetchLatestCoordinate();
    // Poll every 3 seconds for new coordinates
    const interval = setInterval(fetchLatestCoordinate, 3000);
    return () => clearInterval(interval);
  }, []);

  if (loading && !latestDetection) {
    return <div className="flex h-full items-center justify-center text-gray-500 font-medium">Tracking Latest Signal...</div>;
  }

  if (error && !latestDetection) {
    return <div className="p-8 text-red-500 bg-red-50 m-4 rounded">{error}</div>;
  }

  // Default center if somehow no detection is found
  const center = latestDetection 
    ? [latestDetection.latitude, latestDetection.longitude] 
    : [20.5937, 78.9629]; // Default to India

  return (
    <div className="relative h-full w-full flex flex-col">
      {/* Overlay Status Bar */}
      <div className="absolute top-4 left-1/2 -translate-x-1/2 z-[1000] bg-white px-6 py-3 rounded-full shadow-lg border border-green-200 flex items-center gap-3">
        <div className="w-3 h-3 bg-green-500 rounded-full animate-ping"></div>
        <div className="text-sm font-bold text-gray-800">
          {latestDetection ? "LIVE TRACKING: HUMAN DETECTED" : "AWAITING SIGNAL"}
        </div>
      </div>

      <div className="flex-1 w-full relative z-0">
        <MapContainer center={center} zoom={16} style={{ height: '100%', width: '100%' }}>
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <MapUpdater center={center} />
          
          {latestDetection && (
            <Marker position={center} icon={personIcon}>
              <Popup className="custom-popup">
                <div className="p-1">
                  <strong className="text-green-700 block mb-1">Human Detection</strong>
                  <p className="text-xs text-gray-600 mb-2">{latestDetection.location_name}</p>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                    <span className="text-gray-500">Confidence:</span>
                    <span className="font-mono">{(latestDetection.confidence * 100).toFixed(1)}%</span>
                    <span className="text-gray-500">Lat/Lng:</span>
                    <span className="font-mono">{latestDetection.latitude.toFixed(4)}, {latestDetection.longitude.toFixed(4)}</span>
                    <span className="text-gray-500">Last Seen:</span>
                    <span className="font-mono">{new Date(latestDetection.timestamp).toLocaleTimeString()}</span>
                  </div>
                </div>
              </Popup>
            </Marker>
          )}
        </MapContainer>
      </div>
    </div>
  );
};

export default LiveTrackerMap;
