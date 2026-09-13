const { GoogleGenAI } = require('@google/genai');
require('dotenv').config();

let ai;
if (process.env.GEMINI_API_KEY && process.env.GEMINI_API_KEY !== 'your_gemini_api_key_here') {
    ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });
} else {
    console.warn("Gemini API key not configured. Extraction will be skipped.");
}

const SYSTEM_PROMPT = `
You are a disaster intelligence extraction system. 
Given a news article headline and snippet, extract the natural disaster event details into JSON format.

Constraints:
- Track natural disasters AND any major incidents where autonomous rescue robots could be deployed to save lives (e.g., building/bridge collapses, mine cave-ins, industrial explosions, major transport accidents with trapped victims).
- If the article is NOT about a natural disaster or major life-threatening incident, return {"isDisaster": false}
- If it is a relevant event, return a JSON object with:
  {
    "isDisaster": true,
    "type": "earthquake|flood|wildfire|storm|tsunami|cyclone|landslide|structural_collapse|major_accident|other_rescue_event",
    "severity": "low|moderate|high|critical" (estimate based on reported damage/warnings),
    "placeName": "Name of the city, state, country, or region where it is happening",
    "summary": "1-2 sentence summary of the event"
  }
`;

async function extractDisasterInfo(title, snippet) {
    if (!ai) return null;

    try {
        const prompt = `Headline: ${title}\nSnippet: ${snippet}`;
        
        const response = await ai.models.generateContent({
            model: 'gemini-flash-latest',
            contents: prompt,
            config: {
                systemInstruction: SYSTEM_PROMPT,
                responseMimeType: 'application/json',
                temperature: 0.1
            }
        });
        
        const text = response.text;
        const data = JSON.parse(text);
        return data;
    } catch (error) {
        console.error("Error calling Gemini API:", error.message);
        return null;
    }
}

module.exports = { extractDisasterInfo };
