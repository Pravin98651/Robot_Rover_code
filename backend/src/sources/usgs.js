const axios = require('axios');
const geohash = require('ngeohash');

// India bounding box
const INDIA_BBOX = {
    minLat: 6.5,
    maxLat: 37.5,
    minLng: 68.0,
    maxLng: 97.5
};

function isWithinIndia(lat, lng) {
    return lat >= INDIA_BBOX.minLat && lat <= INDIA_BBOX.maxLat &&
           lng >= INDIA_BBOX.minLng && lng <= INDIA_BBOX.maxLng;
}

function determineSeverity(magnitude) {
    if (magnitude < 3) return 'low';
    if (magnitude < 5) return 'moderate';
    if (magnitude < 7) return 'high';
    return 'critical';
}

async function fetchUSGSEarthquakes() {
    try {
        const response = await axios.get('https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_week.geojson');
        const features = response.data.features;
        
        const alerts = [];
        
        for (const feature of features) {
            const properties = feature.properties;
            const geometry = feature.geometry;
            
            if (!geometry || geometry.type !== 'Point') continue;
            
            const [lng, lat, depth] = geometry.coordinates;
            
            if (isWithinIndia(lat, lng)) {
                const magnitude = properties.mag;
                
                // Exclude very minor tremors
                if (magnitude < 2.5) continue;
                
                const severity = determineSeverity(magnitude);
                const timestamp = new Date(properties.time);
                // Expires in 24 hours
                const expiresAt = new Date(timestamp.getTime() + 24 * 60 * 60 * 1000);
                
                const hash = geohash.encode(lat, lng, 6);
                
                alerts.push({
                    type: 'earthquake',
                    severity: severity,
                    confidence: 'verified',
                    title: `Magnitude ${magnitude} Earthquake`,
                    description: properties.place,
                    location: {
                        lat: lat,
                        lng: lng,
                        place: properties.place
                    },
                    radiusKm: 50, // rough estimate based on magnitude
                    geohash: hash,
                    source: 'USGS',
                    sourceEventId: feature.id,
                    reportCount: 1,
                    timestamp: timestamp,
                    expiresAt: expiresAt,
                    active: true,
                    link: properties.url
                });
            }
        }
        
        return alerts;
    } catch (error) {
        console.error("Error fetching USGS data:", error.message);
        return [];
    }
}

module.exports = { fetchUSGSEarthquakes };
