#!/usr/bin/env node
// RSS 日间每小时抓取 - 临时脚本
const https = require('https');
const fs = require('fs');
const xml2js = require('xml2js');

const SENT_FILE = '/root/.openclaw/rss-sent.json';
const TZ_OFFSET = 8; // Asia/Shanghai

function nowShanghai() {
  const d = new Date();
  return new Date(d.getTime() + TZ_OFFSET * 3600000);
}

function parseDate(text) {
  try {
    const d = new Date(text);
    if (isNaN(d)) return null;
    return new Date(d.getTime() + TZ_OFFSET * 3600000);
  } catch { return null; }
}

function todayStart() {
  const d = nowShanghai();
  d.setHours(0, 0, 0, 0);
  return d;
}

function isToday(dt) {
  const start = todayStart();
  const end = nowShanghai();
  return dt >= start && dt <= end;
}

function domainFromUrl(url) {
  try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return 'unknown'; }
}

async function fetchRSS(url) {
  return new Promise((resolve, reject) => {
    https.get(url, { timeout: 15000 }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve(data));
    }).on('error', reject).on('timeout', () => reject(new Error('timeout')));
  });
}

async function parseRSS(xml) {
  const parser = new xml2js.Parser({ explicitArray: false });
  return parser.parseStringPromise(xml);
}

async function main() {
  let sent = [];
  try { sent = JSON.parse(fs.readFileSync(SENT_FILE, 'utf8')); } catch {}
  const sentSet = new Set(sent);

  const feeds = [
    'https://hnrss.org/newest',
    'https://hnrss.org/frontpage',
  ];

  const allArticles = [];

  for (const feed of feeds) {
    try {
      const xml = await fetchRSS(feed);
      const data = await parseRSS(xml);
      const items = data.rss?.channel?.item || [];
      const arr = Array.isArray(items) ? items : [items];
      for (const item of arr) {
        const link = item.link || '';
        const title = (item.title || '').replace(/<!\[CDATA\[(.*?)\]\]>/g, '$1');
        const pubDate = item.pubDate || '';
        const dt = parseDate(pubDate);
        if (dt && isToday(dt) && link && !sentSet.has(link)) {
          allArticles.push({ title, link, pubDate, domain: domainFromUrl(link) });
        }
      }
    } catch (e) {
      console.error('Feed failed:', feed, e.message);
    }
  }

  // 去重
  const seenLinks = new Set();
  const unique = [];
  for (const a of allArticles) {
    if (!seenLinks.has(a.link)) {
      seenLinks.add(a.link);
      unique.push(a);
    }
  }

  // 按时间排序
  unique.sort((a, b) => parseDate(b.pubDate) - parseDate(a.pubDate));

  console.log(JSON.stringify(unique, null, 2));
}

main().catch(console.error);
