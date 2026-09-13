import React, { useEffect, useState } from 'react';
import { Activity, Thermometer, Droplets, Wind, AlertTriangle, ShieldCheck, Wifi, Clock } from 'lucide-react';

const RobotSensors = () => {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const url = 'https://cms-123-e5f66-default-rtdb.firebaseio.com/safetyMonitor/current.json?auth=RX5LotEag2zrW8nDxVodSXFDk14Z5TFUx0vrZEf4';
        const response = await fetch(url);
        if (!response.ok) throw new Error('Failed to fetch sensor data');
        const json = await response.json();
        setData(json);
        setError(null);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 2000); // Poll every 2 seconds
    return () => clearInterval(interval);
  }, []);

  if (loading && !data) {
    return <div className="flex h-full items-center justify-center p-8"><div className="animate-pulse text-lg text-gray-500">Connecting to Robot Telemetry...</div></div>;
  }

  if (error && !data) {
    return <div className="p-8 text-red-500 bg-red-50 m-4 rounded">Error connecting to robot: {error}</div>;
  }

  const { gas, safety, environment, wifi, timestamp_ms, device } = data;

  return (
    <div className="p-6 h-full overflow-y-auto bg-gray-100">
      <div className="max-w-5xl mx-auto space-y-6">
        
        {/* Header */}
        <div className="flex justify-between items-center bg-white p-4 rounded-xl shadow-sm border border-gray-200">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Activity className="text-blue-500" />
              Autonomous Rescue Robot
            </h1>
            <p className="text-sm text-gray-500 font-mono mt-1">{device} • IP: {wifi.ip}</p>
          </div>
          <div className="flex items-center gap-4">
            <div className={`px-4 py-2 rounded-lg font-bold flex items-center gap-2 ${safety.alarm_active ? 'bg-red-100 text-red-700 animate-pulse' : 'bg-green-100 text-green-700'}`}>
              {safety.alarm_active ? <AlertTriangle /> : <ShieldCheck />}
              {safety.reason}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          
          {/* Environment */}
          <div className="bg-white rounded-xl shadow-sm border p-5">
            <h2 className="text-lg font-semibold mb-4 text-gray-700 border-b pb-2 flex items-center gap-2">
              <Thermometer size={18}/> Environment
            </h2>
            <div className="space-y-4">
              <div className="flex justify-between items-center">
                <span className="text-gray-500 flex items-center gap-1"><Thermometer size={16}/> Temp</span>
                <span className="font-bold text-xl">{environment.temperature.toFixed(1)}°C</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-500 flex items-center gap-1"><Droplets size={16}/> Humidity</span>
                <span className="font-bold text-xl">{environment.humidity.toFixed(1)}%</span>
              </div>
              <div className="flex justify-between items-center mt-2 pt-2 border-t text-sm">
                <span className="text-gray-500">Sensor Status</span>
                <span className={environment.dht_ok ? "text-green-500" : "text-red-500"}>{environment.dht_ok ? "ONLINE" : "OFFLINE / INIT"}</span>
              </div>
            </div>
          </div>

          {/* Gas & Air Quality */}
          <div className="bg-white rounded-xl shadow-sm border p-5">
            <h2 className="text-lg font-semibold mb-4 text-gray-700 border-b pb-2 flex items-center gap-2">
              <Wind size={18}/> Gas Sensors (Raw)
            </h2>
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-gray-50 p-3 rounded text-center">
                <p className="text-xs text-gray-500 mb-1">MQ135 (Air)</p>
                <p className="font-mono font-bold text-lg">{gas.mq135}</p>
              </div>
              <div className="bg-gray-50 p-3 rounded text-center">
                <p className="text-xs text-gray-500 mb-1">MQ2 (Smoke)</p>
                <p className="font-mono font-bold text-lg">{gas.mq2}</p>
              </div>
              <div className="bg-gray-50 p-3 rounded text-center">
                <p className="text-xs text-gray-500 mb-1">MQ6 (LPG/Butane)</p>
                <p className="font-mono font-bold text-lg">{gas.mq6}</p>
              </div>
              <div className="bg-gray-50 p-3 rounded text-center">
                <p className="text-xs text-gray-500 mb-1">MQ7 (CO)</p>
                <p className="font-mono font-bold text-lg">{gas.mq7}</p>
              </div>
            </div>
          </div>

          {/* Safety & Motion */}
          <div className="bg-white rounded-xl shadow-sm border p-5">
            <h2 className="text-lg font-semibold mb-4 text-gray-700 border-b pb-2 flex items-center gap-2">
              <ShieldCheck size={18}/> Safety & Motion
            </h2>
            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-gray-500">Motion (PIR)</span>
                <span className={`px-2 py-1 rounded text-xs font-bold ${safety.pir ? 'bg-orange-100 text-orange-700' : 'bg-gray-100 text-gray-500'}`}>
                  {safety.pir ? 'DETECTED' : 'CLEAR'}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-500">Orientation</span>
                <span className={`px-2 py-1 rounded text-xs font-bold ${safety.tilt ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}`}>
                  {safety.tilt ? 'TILTED / FALLEN' : 'UPRIGHT'}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-500">Air Quality Alarm</span>
                <span className={`px-2 py-1 rounded text-xs font-bold ${safety.air_alarm ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}`}>
                  {safety.air_alarm ? 'HAZARDOUS' : 'SAFE'}
                </span>
              </div>
              <div className="flex justify-between items-center mt-2 pt-2 border-t">
                <span className="text-gray-500">Buzzer Status</span>
                <span className={`px-2 py-1 rounded text-xs font-bold ${data.buzzer ? 'bg-red-100 text-red-700 animate-pulse' : 'bg-gray-100 text-gray-500'}`}>
                  {data.buzzer ? 'SOUNDING' : 'SILENT'}
                </span>
              </div>
            </div>
          </div>

        </div>

        {/* Footer info */}
        <div className="flex justify-between text-xs text-gray-400 px-2 mt-4">
          <div className="flex items-center gap-1"><Wifi size={14}/> WiFi RSSI: {wifi.rssi} dBm</div>
          <div className="flex items-center gap-1"><Clock size={14}/> Uptime: {(data.uptime_ms / 1000).toFixed(0)}s</div>
        </div>

      </div>
    </div>
  );
};

export default RobotSensors;
