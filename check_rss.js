const fs = require("fs");
const sqlite3 = require("sqlite3");

const sentPath = "/root/.openclaw/rss-sent.json";
let sent = [];
try {
  sent = JSON.parse(fs.readFileSync(sentPath, "utf-8"));
} catch(e) {}

const db = new sqlite3.Database("/root/.config/rss-viewer/feeds.db");
const todayStart = "2026-08-15 00:00:00";
const now = "2026-08-15 17:33:00";

const sql = `
  SELECT title, link, summary, content, published_at 
  FROM articles 
  WHERE published_at >= ? AND published_at <= ? 
  ORDER BY published_at DESC
`;

db.all(sql, [todayStart, now], (err, rows) => {
  if (err) { console.error(err); process.exit(1); }
  const newArticles = rows.filter(r => !sent.includes(r.link));
  console.log(JSON.stringify({
    totalToday: rows.length,
    alreadySent: rows.length - newArticles.length,
    newCount: newArticles.length,
    articles: newArticles.map(r => ({
      title: r.title,
      link: r.link,
      summary: (r.summary || "").slice(0, 500),
      content: (r.content || "").slice(0, 1000),
      published: r.published_at
    }))
  }, null, 2));
  db.close();
});
