const https = require('https');
const fs = require('fs');
const path = require('path');

const RSS_URL = 'https://thinkpeace.github.io/rss-cache/feeds/fulltext-72h.xml';
const SENT_FILE = process.env.SENT_FILE || path.join(require('os').homedir(), '.openclaw', 'rss-sent.json');

function fetchXML(url) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { timeout: 30000 }, (res) => {
      if (res.statusCode !== 200) {
        return reject(new Error(`HTTP ${res.statusCode}`));
      }
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => resolve(data));
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(new Error('timeout')); });
  });
}

function parseRSS(xml) {
  const items = [];
  const itemRegex = /<item>([\s\S]*?)<\/item>/g;
  let m;
  while ((m = itemRegex.exec(xml)) !== null) {
    const itemXML = m[1];
    const getTag = (tag) => {
      const re = new RegExp(`<${tag}[\\s\S]*?>([\\s\\S]*?)<\\/${tag}>`);
      const match = itemXML.match(re);
      return match ? match[1].trim() : '';
    };
    const linkMatch = itemXML.match(/<link>([\s\S]*?)<\/link>/);
    const url = linkMatch ? linkMatch[1].trim() : '';
    items.push({
      title: getTag('title'),
      link: url,
      pubDate: getTag('pubDate'),
      description: getTag('description'),
      source: getTag('source') || (url ? new URL(url).hostname.replace(/^www\./, '') : '')
    });
  }
  return items;
}

function getTodayRange() {
  const now = new Date();
  const tzOffset = 8 * 60; // Asia/Shanghai = UTC+8 in minutes
  const tzNow = new Date(now.getTime() + tzOffset * 60 * 1000);
  const startOfDay = new Date(tzNow);
  startOfDay.setUTCHours(0, 0, 0, 0);
  const endOfDay = new Date(tzNow);
  // Current time is the upper bound
  return {
    start: new Date(startOfDay.getTime() - tzOffset * 60 * 1000),
    end: now
  };
}

function parsePubDate(str) {
  if (!str) return null;
  try {
    const d = new Date(str);
    if (isNaN(d.getTime())) return null;
    return d;
  } catch { return null; }
}

async function main() {
  // Load sent URLs
  let sentUrls = [];
  try {
    const raw = fs.readFileSync(SENT_FILE, 'utf-8');
    sentUrls = JSON.parse(raw);
  } catch { /* ignore */ }

  const sentSet = new Set(sentUrls);

  const xml = await fetchXML(RSS_URL);
  const items = parseRSS(xml);

  const { start, end } = getTodayRange();

  const newItems = items.filter(item => {
    const pub = parsePubDate(item.pubDate);
    if (!pub) return false;
    return pub >= start && pub <= end && !sentSet.has(item.link);
  });

  if (newItems.length === 0) {
    console.log('NO_NEW_ARTICLES');
    return;
  }

  // Output items as JSON
  console.log(JSON.stringify(newItems, null, 2));
}

main().catch(err => {
  console.error('ERROR:', err.message);
  process.exit(1);
});
