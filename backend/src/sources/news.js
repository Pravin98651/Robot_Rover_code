const Parser = require('rss-parser');
const parser = new Parser();

const INDIAN_PUBLISHERS = [
    'ndtv', 'times of india', 'the hindu', 'indian express', 'hindustan times', 
    'news18', 'india today', 'livemint', 'firstpost', 'the wire', 'scroll',
    'business standard', 'deccan herald', 'telegraph india', 'tribune india',
    'ani', 'ptinews'
];

function isIndianPublisher(sourceName) {
    if (!sourceName) return false;
    const lowerSource = sourceName.toLowerCase();
    
    for (const pub of INDIAN_PUBLISHERS) {
        if (lowerSource.includes(pub)) {
            return true;
        }
    }
    
    return false;
}



async function fetchIndiaNewsRSS() {
    const keywords = 'earthquake OR flood OR wildfire OR cyclone OR tsunami OR landslide OR "building collapse" OR "bridge collapse" OR "mine collapse" OR "industrial accident" OR "train derailment" OR "trapped"';
    
    const languages = [
        { hl: "en-IN", label: "English", ceid: "IN:en" }
    ];

    const allArticles = [];

    for (const lang of languages) {
        const url = `https://news.google.com/rss/search?q=${encodeURIComponent(keywords)}&hl=${lang.hl}&gl=IN&ceid=${lang.ceid}`;
        try {
            const feed = await parser.parseURL(url);
            
            // Filter recent articles (last 7 days) and by authentic Indian publisher
            const lastWeek = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
            
            for (const item of feed.items) {
                const pubDate = new Date(item.pubDate);
                if (pubDate > lastWeek && isIndianPublisher(item.source)) {
                    allArticles.push({
                        title: item.title,
                        link: item.link,
                        pubDate: pubDate,
                        contentSnippet: item.contentSnippet || item.content,
                        source: item.source || 'News'
                    });
                }
            }
        } catch (error) {
            console.error(`Error fetching news for ${lang.label}:`, error.message);
        }
    }
    
    // Sort by newest
    allArticles.sort((a, b) => b.pubDate - a.pubDate);
    
    // Return top 20 to avoid overwhelming Gemini API limits during testing
    return allArticles.slice(0, 20);
}

module.exports = { fetchIndiaNewsRSS };
