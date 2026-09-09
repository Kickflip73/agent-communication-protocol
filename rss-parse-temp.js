const https = require('https');
const xml2js = require('xml2js');
const fs = require('fs');

const feedUrl = 'https://thinkpeace.github.io/rss-cache/feeds/fulltext-72h.xml';
const sentFile = '/root/.openclaw/rss-sent.json';

function fetch(url) {
  return new Promise((resolve, reject) => {
    https.get(url, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve(data));
    }).on('error', reject);
  });
}

async function main() {
  const xml = await fetch(feedUrl);
  const parser = new xml2js.Parser();
  const result = await parser.parseStringPromise(xml);

  const items = result.rss.channel[0].item || [];

  // Load sent URLs
  let sentUrls = [];
  if (fs.existsSync(sentFile)) {
    try {
      sentUrls = JSON.parse(fs.readFileSync(sentFile, 'utf8'));
    } catch (e) {
      sentUrls = [];
    }
  }

  // Today in Shanghai: 2026-07-25
  const todayStart = new Date('2026-07-24T16:00:00Z'); // 2026-07-25 00:00 Shanghai
  const now = new Date('2026-07-25T04:00:00Z'); // Current time: 12:00 Shanghai

  const todayItems = items.filter(item => {
    if (!item.pubDate || !item.pubDate[0]) return false;
    const pubDate = new Date(item.pubDate[0]);
    return pubDate >= todayStart && pubDate <= now;
  }).filter(item => {
    const link = item.link ? item.link[0] : '';
    return !sentUrls.includes(link);
  });

  console.log(JSON.stringify(todayItems.map(item => ({
    title: item.title ? item.title[0] : '',
    link: item.link ? item.link[0] : '',
    pubDate: item.pubDate ? item.pubDate[0] : '',
    description: item.description ? item.description[0] : ''
  })), null, 2));
}

main().catch(console.error);
