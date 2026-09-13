import React from 'react';
import { MapContainer, TileLayer, Marker, Popup, Circle } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import { formatDistanceToNow } from 'date-fns';

// Fix for default marker icons in react-leaflet
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

// Custom icons based on confidence
const verifiedIcon = new L.Icon({
  iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-red.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41]
});

const reportedIcon = new L.Icon({
  iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-orange.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41]
});

const AlertMap = ({ alerts }) => {
  // Center of India
  const center = [20.5937, 78.9629];
  
  const getSeverityColor = (severity) => {
    switch (severity) {
      case 'critical': return '#dc2626';
      case 'high': return '#ea580c';
      case 'moderate': return '#eab308';
      default: return '#3b82f6';
    }
  };

  return (
    <div style={{ height: '100%', width: '100%' }}>
      <MapContainer center={center} zoom={5} style={{ height: '100%', width: '100%' }}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        
        {alerts.map(alert => (
          <React.Fragment key={alert.id}>
            <Marker 
              position={[alert.location.lat, alert.location.lng]}
              icon={alert.confidence === 'verified' ? verifiedIcon : reportedIcon}
            >
              <Popup>
                <div className="p-1">
                  <h3 className="font-bold text-lg capitalize">{alert.type}</h3>
                  <p className="text-sm font-medium mb-1">
                    {alert.location.place}
                  </p>
                  <p className="text-xs text-gray-500 mb-2 font-mono">
                    {alert.location.lat.toFixed(4)}, {alert.location.lng.toFixed(4)}
                  </p>
                  <p className="text-sm text-gray-600 mb-2">
                    {alert.title}
                  </p>
                  <div className="flex gap-2 mb-2">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium bg-gray-100 border ${alert.confidence === 'verified' ? 'border-red-300 text-red-700' : 'border-orange-300 text-orange-700'}`}>
                      {alert.confidence === 'verified' ? 'Verified (Sensor)' : 'Reported (News)'}
                    </span>
                    <span className="px-2 py-0.5 rounded text-xs font-medium bg-gray-100 capitalize">
                      Severity: {alert.severity}
                    </span>
                  </div>
                  <p className="text-xs text-gray-400">
                    Source:{' '}
                    {alert.link ? (
                      <a href={alert.link} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline">
                        {alert.source}
                      </a>
                    ) : (
                      alert.source
                    )}
                    {' '}• Detected {formatDistanceToNow(alert.timestamp.toDate(), { addSuffix: true })}
                  </p>
                </div>
              </Popup>
            </Marker>
            <Circle 
              center={[alert.location.lat, alert.location.lng]}
              radius={alert.radiusKm * 1000}
              pathOptions={{
                fillColor: getSeverityColor(alert.severity),
                fillOpacity: 0.2,
                color: getSeverityColor(alert.severity),
                weight: 1
              }}
            />
          </React.Fragment>
        ))}
      </MapContainer>
    </div>
  );
};

export default AlertMap;
