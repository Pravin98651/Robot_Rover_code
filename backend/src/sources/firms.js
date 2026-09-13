const axios = require('axios');
const geohash = require('ngeohash');
require('dotenv').config();

function determineSeverity(frp) {
    // FRP (Fire Radiative Power) gives an indication of the fire's intensity
    if (frp < 50) return 'low';
    if (frp < 150) return 'moderate';
    if (frp < 400) return 'high';
    return 'critical';
}

async function fetchFIRMSWildfires() {
    const apiKey = process.env.FIRMS_API_KEY;
    if (!apiKey || apiKey === 'your_nasa_firms_api_key_here') {
        console.warn("NASA FIRMS API key not configured. Skipping FIRMS fetch.");
        return [];
    }

    // India bounding box
    const bbox = '68,6.5,97.5,37.5';
    // Fetch fires from the last 1 day (max for area query)
    const dayRange = 1;
    // Source: VIIRS SNPP NRT
    const source = 'VIIRS_SNPP_NRT';
    
    const url = `https://firms.modaps.eosdis.nasa.gov/api/area/csv/${apiKey}/${source}/${bbox}/${dayRange}`;

    try {
        const response = await axios.get(url);
        const csvData = response.data;
        
        // Basic CSV parsing
        const lines = csvData.split('\n');
        if (lines.length <= 1) return []; // Only header or empty
        
        const headers = lines[0].split(',');
        const alerts = [];
        const now = new Date();
        
        // FIRMS CSV headers usually: latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight
        const latIdx = headers.indexOf('latitude');
        const lngIdx = headers.indexOf('longitude');
        const frpIdx = headers.indexOf('frp');
        const acqDateIdx = headers.indexOf('acq_date');
        const acqTimeIdx = headers.indexOf('acq_time');
        
        if (latIdx === -1 || lngIdx === -1) {
            console.error("Unexpected FIRMS CSV format");
            return [];
        }

        // We'll cluster nearby fires to avoid overwhelming the DB, but for PoC we'll insert them and let geohash grouping handle it somewhat.
        // Actually, returning every single thermal anomaly as an alert is too much. 
        // Let's only return high intensity fires for the alert system.
        
        for (let i = 1; i < lines.length; i++) {
            const line = lines[i].trim();
            if (!line) continue;
            
            const values = line.split(',');
            const lat = parseFloat(values[latIdx]);
            const lng = parseFloat(values[lngIdx]);
            const frp = parseFloat(values[frpIdx]);
            
            // Only alert on significant fires (e.g. FRP > 100)
            if (frp < 100) continue;
            
            const severity = determineSeverity(frp);
            
            // Create a timestamp from acq_date and acq_time
            // acq_date: YYYY-MM-DD, acq_time: HHMM (UTC)
            const dateStr = values[acqDateIdx];
            const timeStr = values[acqTimeIdx].padStart(4, '0');
            const timestampStr = `${dateStr}T${timeStr.substring(0,2)}:${timeStr.substring(2,4)}:00Z`;
            const timestamp = new Date(timestampStr);
            
            const expiresAt = new Date(now.getTime() + 12 * 60 * 60 * 1000); // Expires in 12h
            
            const hash = geohash.encode(lat, lng, 6);
            // Create a pseudo-unique ID based on date, lat, lng rounded
            const eventId = `firms_${dateStr}_${lat.toFixed(2)}_${lng.toFixed(2)}`;
            
            alerts.push({
                type: 'wildfire',
                severity: severity,
                confidence: 'verified',
                title: 'Active Wildfire Detected',
                description: `Wildfire detected with Fire Radiative Power (FRP) of ${frp} MW.`,
                location: {
                    lat: lat,
                    lng: lng,
                    place: 'Unknown Location (Sensor data)' // Reverse geocoding could be applied later
                },
                radiusKm: 10,
                geohash: hash,
                source: 'FIRMS',
                sourceEventId: eventId,
                reportCount: 1,
                timestamp: timestamp,
                expiresAt: expiresAt,
                active: true
            });
        }
        
        // Basic deduplication on our side based on eventId (since we rounded lat/lng)
        const deduped = [];
        const seen = new Set();
        for (const alert of alerts) {
            if (!seen.has(alert.sourceEventId)) {
                seen.add(alert.sourceEventId);
                deduped.push(alert);
            }
        }
        
        return deduped;
    } catch (error) {
        console.error("Error fetching FIRMS data:", error.message);
        return [];
    }
}

module.exports = { fetchFIRMSWildfires };
