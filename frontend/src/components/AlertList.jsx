import React from 'react';
import { formatDistanceToNow } from 'date-fns';
import { AlertTriangle, Flame, Waves, Wind, Mountain, Radio, Newspaper, Building } from 'lucide-react';

const typeIcons = {
  earthquake: <Mountain size={18} />,
  wildfire: <Flame size={18} />,
  flood: <Waves size={18} />,
  storm: <Wind size={18} />,
  cyclone: <Wind size={18} />,
  tsunami: <Waves size={18} />,
  landslide: <Mountain size={18} />,
  structural_collapse: <Building size={18} />,
  major_accident: <AlertTriangle size={18} />,
  other_rescue_event: <AlertTriangle size={18} />,
  default: <AlertTriangle size={18} />
};

const AlertList = ({ alerts, onSelectAlert }) => {
  if (alerts.length === 0) {
    return (
      <div className="p-8 text-center text-gray-500">
        <AlertTriangle size={32} className="mx-auto mb-2 opacity-50" />
        <p>No active alerts at this time.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="p-4 border-b bg-white flex justify-between items-center shrink-0">
        <h2 className="font-bold text-lg flex items-center gap-2">
          <AlertTriangle className="text-red-500" />
          Active Alerts ({alerts.length})
        </h2>
      </div>
      
      <div className="flex-1 overflow-y-auto bg-gray-50 p-2">
        {alerts.map(alert => (
          <div 
            key={alert.id}
            onClick={() => onSelectAlert(alert)}
            className="mb-3 bg-white border rounded-lg p-3 shadow-sm hover:shadow-md transition-shadow cursor-pointer border-l-4"
            style={{ 
              borderLeftColor: alert.severity === 'critical' ? '#dc2626' : 
                               alert.severity === 'high' ? '#ea580c' : 
                               alert.severity === 'moderate' ? '#eab308' : '#3b82f6'
            }}
          >
            <div className="flex justify-between items-start mb-2">
              <div className="flex items-center gap-2">
                <span className={`p-1.5 rounded-full ${alert.confidence === 'verified' ? 'bg-red-100 text-red-600' : 'bg-orange-100 text-orange-600'}`}>
                  {typeIcons[alert.type] || typeIcons.default}
                </span>
                <span className="font-semibold capitalize text-gray-800">{alert.type}</span>
              </div>
              <span className="text-xs text-gray-500 whitespace-nowrap">
                {formatDistanceToNow(alert.timestamp.toDate(), { addSuffix: true })}
              </span>
            </div>
            
            <h3 className="text-sm font-medium text-gray-900 mb-0.5">{alert.location.place}</h3>
            <p className="text-xs text-gray-400 font-mono mb-2">{alert.location.lat.toFixed(4)}, {alert.location.lng.toFixed(4)}</p>
            <p className="text-sm text-gray-600 line-clamp-2 mb-3">{alert.title}</p>
            
            <div className="flex items-center justify-between text-xs">
              <span className="flex items-center gap-1 text-gray-500 font-medium truncate max-w-[200px]">
                {alert.confidence === 'verified' ? <Radio size={12} className="text-red-500 shrink-0"/> : <Newspaper size={12} className="text-orange-500 shrink-0"/>}
                {alert.link ? (
                  <a href={alert.link} target="_blank" rel="noopener noreferrer" className="hover:underline text-blue-600 truncate" onClick={(e) => e.stopPropagation()}>
                    {alert.source}
                  </a>
                ) : (
                  alert.source
                )}
              </span>
              <span className="px-2 py-0.5 bg-gray-100 rounded capitalize font-medium text-gray-600">
                {alert.severity}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default AlertList;
