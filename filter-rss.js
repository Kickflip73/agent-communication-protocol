const fs = require('fs');

// Current time: 2026-07-22 12:10 Asia/Shanghai = 2026-07-22 04:10 UTC
const now = new Date('2026-07-22T04:10:00Z');
const todayStart = new Date('2026-07-21T16:00:00Z'); // 2026-07-22 00:00 Shanghai

const sentUrls = JSON.parse(fs.readFileSync('/root/.openclaw/rss-sent.json', 'utf8'));
const sentSet = new Set(sentUrls);

const articles = JSON.parse(fs.readFileSync('/root/.openclaw/workspace/articles.json', 'utf8'));

const newArticles = articles.filter(a => {
  const pubDate = new Date(a.published_at);
  return pubDate >= todayStart && pubDate <= now && !sentSet.has(a.link);
});

console.log(`Total articles today: ${articles.length}`);
console.log(`Already sent: ${sentSet.size}`);
console.log(`New articles: ${newArticles.length}`);

if (newArticles.length > 0) {
  newArticles.forEach((a, i) => {
    console.log(`\n${i+1}. ${a.title}`);
    console.log(`   Link: ${a.link}`);
    console.log(`   Published: ${a.published_at}`);
  });
}
