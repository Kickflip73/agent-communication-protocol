const fs = require('fs');

const sentUrls = JSON.parse(fs.readFileSync('~/.openclaw/rss-sent.json', 'utf8'));
const articles = JSON.parse(fs.readFileSync('/root/.openclaw/workspace/rss-today-articles.json', 'utf8'));

const today = '2026-08-22';
const newArticles = articles.filter(a => a.date === today && !sentUrls.includes(a.url));

console.log(JSON.stringify(newArticles, null, 2));
console.log(`\nTotal new articles today: ${newArticles.length}`);
