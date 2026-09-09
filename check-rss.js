const fs = require('fs');
const sqlite3 = require('sqlite3').verbose();

// Read sent URLs
const sentPath = '/root/.openclaw/rss-sent.json';
const sentUrls = fs.existsSync(sentPath) ? JSON.parse(fs.readFileSync(sentPath, 'utf8')) : [];
const sentSet = new Set(sentUrls);

// Open DB
const db = new sqlite3.Database('/root/.config/rss-viewer/feeds.db');

// Get today's start in Shanghai time
const now = new Date();
const shanghaiOffset = 8 * 60 * 60 * 1000;
const todayStart = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()) - shanghaiOffset);
const todayStartISO = todayStart.toISOString();
const nowISO = now.toISOString();

console.log('Today start (UTC):', todayStartISO);
console.log('Now (UTC):', nowISO);
console.log('Sent URLs count:', sentSet.size);

db.all(
  `SELECT title, link, published_at FROM articles WHERE published_at >= ? AND published_at <= ? ORDER BY published_at DESC`,
  [todayStartISO, nowISO],
  (err, rows) => {
    if (err) {
      console.error(err);
      process.exit(1);
    }
    
    console.log('Total articles from today:', rows.length);
    
    const newArticles = rows.filter(r => !sentSet.has(r.url));
    console.log('New articles not in sent list:', newArticles.length);
    
    newArticles.forEach((a, i) => {
      console.log(`${i+1}. ${a.title}`);
      console.log(`   URL: ${a.link}`);
      console.log(`   Published: ${a.published_at}`);
    });
    
    db.close();
  }
);
