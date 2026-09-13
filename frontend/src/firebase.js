import { initializeApp } from "firebase/app";
import { getFirestore } from "firebase/firestore";
import { getAnalytics } from "firebase/analytics";

const firebaseConfig = {
  apiKey: "AIzaSyCpQfWA9QBO0xW8ylCUuXUDOD4Er1idrx0",
  authDomain: "newsdetection-7d302.firebaseapp.com",
  projectId: "newsdetection-7d302",
  storageBucket: "newsdetection-7d302.firebasestorage.app",
  messagingSenderId: "341156248145",
  appId: "1:341156248145:web:6348637e3865334a355670",
  measurementId: "G-P6QJV7NJEN"
};

const app = initializeApp(firebaseConfig);
export const analytics = getAnalytics(app);
export const db = getFirestore(app);
