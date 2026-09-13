const cron = require('node-cron');
const geohash = require('ngeohash');
const { initFirebase } = require('./firebase');
const { fetchUSGSEarthquakes } = require('./sources/usgs');
const { fetchFIRMSWildfires } = require('./sources/firms');
const { fetchIndiaNewsRSS } = require('./sources/news');
const { extractDisasterInfo } = require('./processors/gemini');
const { geocodePlaceName } = require('./processors/geocoder');

// Initialize DB
const db = initFirebase();

async function saveAlertsToFirestore(alerts) {
    if (!db) {
        console.log(`Skipping DB write. ${alerts.length} alerts would have been saved.`);
        return;
    }

    const batch = db.batch();
    const alertsRef = db.collection('alerts');
    
    let count = 0;
    for (const alert of alerts) {
        // Use sourceEventId as document ID for idempotency
        const docRef = alertsRef.doc(alert.sourceEventId);
        
        // We use set with merge: true to avoid overwriting existing data entirely
        // and instead update fields (or create new if it doesn't exist)
        batch.set(docRef, alert, { merge: true });
        count++;
        
        // Firestore batches support up to 500 writes
        if (count === 500) {
            await batch.commit();
            count = 0;
        }
    }
    
    if (count > 0) {
        await batch.commit();
    }
    console.log(`Successfully synced ${alerts.length} alerts to Firestore.`);
}

async function processStructuredSources() {
    console.log("Fetching structured sources (USGS, FIRMS)...");
    
    const usgsAlerts = await fetchUSGSEarthquakes();
    const firmsAlerts = await fetchFIRMSWildfires();
    
    const allAlerts = [...usgsAlerts, ...firmsAlerts];
    
    if (allAlerts.length > 0) {
        await saveAlertsToFirestore(allAlerts);
    } else {
        console.log("No structured alerts found.");
    }
}

async function processUnstructuredSources() {
    console.log("Fetching unstructured sources (News)...");
    
    const articles = await fetchIndiaNewsRSS();
    console.log(`Found ${articles.length} recent news articles from Indian publishers.`);
    
    const alerts = [];
    const now = new Date();
    
    for (const article of articles) {
        // Step 1: Extract via Gemini
        const info = await extractDisasterInfo(article.title, article.contentSnippet);
        
        if (info && info.isDisaster) {
            console.log(`Extracted disaster: ${info.type} in ${info.placeName} (Severity: ${info.severity})`);
            
            // Step 2: Geocode
            const location = await geocodePlaceName(info.placeName);
            
            if (location) {
                const hash = geohash.encode(location.lat, location.lng, 6);
                
                // Create unique ID based on link to avoid duplicate news alerts
                const safeLink = article.link.replace(/[^a-zA-Z0-9]/g, '_').substring(0, 50);
                const eventId = `news_${safeLink}`;
                
                alerts.push({
                    type: info.type,
                    severity: info.severity,
                    confidence: 'reported',
                    title: info.summary || article.title,
                    description: `Source: ${article.source}. ${article.title}`,
                    location: {
                        lat: location.lat,
                        lng: location.lng,
                        place: info.placeName
                    },
                    radiusKm: 25,
                    geohash: hash,
                    source: `News: ${article.source}`,
                    sourceEventId: eventId,
                    reportCount: 1,
                    timestamp: new Date(article.pubDate),
                    expiresAt: new Date(now.getTime() + 24 * 60 * 60 * 1000), // Expires in 24h
                    active: true,
                    link: article.link
                });
            }
        }
        
        // Add a small delay to respect API rate limits (Gemini / Geocoder)
        await new Promise(resolve => setTimeout(resolve, 1000));
    }
    
    if (alerts.length > 0) {
        await saveAlertsToFirestore(alerts);
    }
}

async function runEngine() {
    console.log(`[${new Date().toISOString()}] Starting disaster alert ingestion engine run...`);
    try {
        await processStructuredSources();
        await processUnstructuredSources();
        console.log(`[${new Date().toISOString()}] Engine run completed successfully.`);
    } catch (error) {
        console.error(`[${new Date().toISOString()}] Engine run failed:`, error);
    }
}

// Run immediately on startup
runEngine();

// Schedule to run every 15 minutes
cron.schedule('*/15 * * * *', () => {
    runEngine();
});

console.log("Disaster Alert Ingestion Engine is running. Polling every 15 minutes.");
