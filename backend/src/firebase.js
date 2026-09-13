const { initializeApp, cert, getApps } = require('firebase-admin/app');
const { getFirestore } = require('firebase-admin/firestore');
const path = require('path');
require('dotenv').config();

let db;

function initFirebase() {
    if (getApps().length > 0) {
        db = getFirestore();
        return db;
    }

    try {
        const keyPath = process.env.FIREBASE_SERVICE_ACCOUNT_KEY_PATH || './serviceAccountKey.json';
        const serviceAccount = require(path.resolve(process.cwd(), keyPath));

        initializeApp({
            credential: cert(serviceAccount)
        });

        db = getFirestore();
        console.log("Firebase Admin Initialized Successfully");
    } catch (error) {
        console.error("Failed to initialize Firebase Admin:", error.message);
        console.error("Make sure you have downloaded the serviceAccountKey.json from Firebase console.");
        return null; 
    }
    
    return db;
}

module.exports = { initFirebase };
