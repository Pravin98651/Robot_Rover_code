import React, { useState, useEffect } from 'react';
import { collection, query, where, onSnapshot } from 'firebase/firestore';
import { db } from './firebase';
import AlertMap from './components/AlertMap';
import AlertList from './components/AlertList';

import RobotSensors from './components/RobotSensors';
import LiveTrackerMap from './components/LiveTrackerMap';
import { ShieldAlert, Activity, Crosshair } from 'lucide-react';

function App() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedAlert, setSelectedAlert] = useState(null);
  const [activeTab, setActiveTab] = useState('map');

  useEffect(() => {
    // Listen to active alerts
    const q = query(
      collection(db, 'alerts'),
      where('active', '==', true)
    );

    const unsubscribe = onSnapshot(q, (snapshot) => {
      const activeAlerts = [];
      snapshot.forEach((doc) => {
        activeAlerts.push({ id: doc.id, ...doc.data() });
      });
      // Sort by newest first
      activeAlerts.sort((a, b) => b.timestamp.toMillis() - a.timestamp.toMillis());
      setAlerts(activeAlerts);
      setLoading(false);
    }, (error) => {
      console.error("Error listening to alerts:", error);
      setLoading(false); // Make sure it stops loading even on error
    });

    return () => unsubscribe();
  }, []);

  return (
    <div className="flex flex-col h-screen w-full bg-gray-100 font-sans">
      {/* Top Navbar */}
      <header className="bg-gray-900 text-white p-3 flex gap-4 shrink-0 shadow-md relative z-20">
        <div className="font-bold text-xl mr-6 flex items-center gap-2">
          <ShieldAlert className="text-red-500"/> DISASTER WATCH
        </div>
        <button 
          onClick={() => setActiveTab('map')}
          className={`px-4 py-1 rounded-md font-medium flex items-center gap-2 ${activeTab === 'map' ? 'bg-blue-600' : 'hover:bg-gray-800'}`}
        >
          <ShieldAlert size={18}/> Alert Map
        </button>
        <button 
          onClick={() => setActiveTab('robot')}
          className={`px-4 py-1 rounded-md font-medium flex items-center gap-2 ${activeTab === 'robot' ? 'bg-blue-600' : 'hover:bg-gray-800'}`}
        >
          <Activity size={18}/> Robot Telemetry
        </button>
        <button 
          onClick={() => setActiveTab('tracker')}
          className={`px-4 py-1 rounded-md font-medium flex items-center gap-2 ${activeTab === 'tracker' ? 'bg-green-600' : 'hover:bg-gray-800'}`}
        >
          <Crosshair size={18}/> Live Tracker
        </button>
      </header>

      {/* Main Content */}
      <div className="flex flex-1 overflow-hidden">
        {activeTab === 'map' && (
          <>
            <div className="w-96 shrink-0 bg-white shadow-lg z-10 border-r border-gray-200">
              {loading ? (
                <div className="p-8 text-center text-gray-500">Loading alerts...</div>
              ) : (
                <AlertList 
                  alerts={alerts} 
                  onSelectAlert={(alert) => setSelectedAlert(alert)} 
                />
              )}
            </div>
            <div className="flex-1 relative z-0">
              <AlertMap alerts={alerts} selectedAlert={selectedAlert} />
            </div>
          </>
        )}
        
        {activeTab === 'robot' && (
          <div className="flex-1 w-full relative z-0">
            <RobotSensors />
          </div>
        )}

        {activeTab === 'tracker' && (
          <div className="flex-1 w-full relative z-0">
            <LiveTrackerMap />
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
