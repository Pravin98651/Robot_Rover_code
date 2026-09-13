const axios = require('axios');
require('dotenv').config();

// Ensure we don't hit Nominatim more than 1 request per second
const delay = ms => new Promise(res => setTimeout(res, ms));
let lastGeocodeTime = 0;

async function geocodePlaceName(placeName) {
    // Throttle to respect Nominatim usage policy (1 request/sec)
    const now = Date.now();
    const timeSinceLastRequest = now - lastGeocodeTime;
    if (timeSinceLastRequest < 1100) {
        await delay(1100 - timeSinceLastRequest);
    }
    lastGeocodeTime = Date.now();

    try {
        // Bias strictly to India (countrycodes=in) using Nominatim OpenStreetMap
        const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(placeName)}&countrycodes=in&format=json&limit=1`;
        
        // Nominatim requires a valid User-Agent
        const response = await axios.get(url, {
            headers: {
                'User-Agent': 'DisasterAlertSystem/1.0 (PoC)'
            }
        });
        
        if (response.data && response.data.length > 0) {
            const result = response.data[0];
            
            return {
                lat: parseFloat(result.lat),
                lng: parseFloat(result.lon),
                place: result.display_name
            };
        } else {
            console.warn(`Geocoding failed or no results for place: ${placeName}`);
            return null;
        }
    } catch (error) {
        console.error("Error calling Nominatim Geocoding API:", error.message);
        return null;
    }
}

module.exports = { geocodePlaceName };
