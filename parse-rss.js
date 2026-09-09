const sqlite3 = require('sqlite3').verbose();
const fs = require('fs');

const db = new sqlite3.Database('/root/.config/rss-viewer/feeds.db');

// 今天 0:00:00 Asia/Shanghai -> UTC
const today = new Date('2026-08-21T00:00:00+08:00');
const now = new Date('2026-08-21T19:45:00+08:00');

const sentUrls = JSON.parse(fs.readFileSync('/root/.openclaw/rss-sent.json', 'utf8'));

const articles = [];

db.each(`
  SELECT a.title, a.link, a.published_at, f.url as feed_url, f.title as feed_title
  FROM articles a
  JOIN feeds f ON a.feed_id = f.id
  ORDER BY a.published_at DESC
`, (err, row) => {
  if (err) {
    console.error(err);
    return;
  }

  const pubDate = new Date(row.published_at);
  
  // 检查是否在今天范围内
  if (pubDate >= today && pubDate <= now) {
    // 检查是否已发送
    if (!sentUrls.includes(row.link)) {
      articles.push({
        title: row.title,
        link: row.link,
        pubDate: row.published_at,
        feedTitle: row.feed_title,
        feedUrl: row.feed_url
      });
    }
  }
}, (err) => {
  if (err) {
    console.error(err);
    return;
  }
  
  console.log(JSON.stringify(articles, null, 2));
  console.log(`\n共 ${articles.length} 篇新文章`);
  
  db.close();
});
