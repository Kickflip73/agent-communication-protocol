const https = require('https');
const xml2js = require('xml2js');

const feedUrl = 'https://thinkpeace.github.io/rss-cache/feeds/fulltext-72h.xml';

function fetchXml(url) {
  return new Promise((resolve, reject) => {
    https.get(url, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve(data));
    }).on('error', reject);
  });
}

async function main() {
  try {
    const xml = await fetchXml(feedUrl);
    const parser = new xml2js.Parser({ explicitArray: false });
    const result = await parser.parseStringPromise(xml);
    
    const items = result.rss?.channel?.item || [];
    const arr = Array.isArray(items) ? items : [items];
    
    // 按日期排序，最新在前
    arr.sort((a, b) => new Date(b.pubDate) - new Date(a.pubDate));
    
    // 统计
    console.log(`Total items: ${arr.length}`);
    console.log(`First 5:`);
    arr.slice(0, 5).forEach(item => {
      console.log(`- ${item.pubDate}: ${item.title?.substring(0, 80)}...`);
      console.log(`  Link: ${item.link}`);
    });
  } catch (e) {
    console.error(e.message);
  }
}

main();
