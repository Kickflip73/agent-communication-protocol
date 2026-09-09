const fs = require('fs');

const SENT_FILE = process.env.HOME + '/.openclaw/rss-sent.json';
let sent = [];
try {
  sent = JSON.parse(fs.readFileSync(SENT_FILE, 'utf8'));
} catch(e) {}

let data = '';
process.stdin.on('data', chunk => data += chunk);
process.stdin.on('end', () => {
  try {
    const articles = JSON.parse(data);
    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0);
    
    const newArticles = articles.filter(a => {
      const pubDate = new Date(a.published);
      const isToday = pubDate >= todayStart && pubDate <= now;
      const notSent = !sent.includes(a.url);
      return isToday && notSent;
    });
    
    console.log(JSON.stringify(newArticles, null, 2));
  } catch(e) {
    console.error('Error:', e.message);
    process.exit(1);
  }
});
