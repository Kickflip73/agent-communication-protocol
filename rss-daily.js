#!/usr/bin/env node
/**
 * RSS 日报推送 - 备用方案（当 rss-agent-viewer 不可用时）
 * 使用 curl 直接获取 HN RSS 并解析，不抓取全文，使用 AI 摘要
 */
const fs = require('fs');
const path = require('path');

const SENT_FILE = path.join(process.env.HOME, '.openclaw', 'rss-sent.json');
const FEED_URL = 'https://hnrss.org/newest?points=50';

const now = new Date();
const nowUTC = now.toISOString();
const todayStartUTC = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0)).toISOString();

function toBeijingHH(d) {
  const beijing = new Date(d.getTime() + 8 * 60 * 60 * 1000);
  return String(beijing.getHours()).padStart(2, '0') + ':00';
}

function getDomain(url) {
  try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return 'unknown'; }
}

function parsePubDate(str) { return new Date(str).toISOString(); }

let sentUrls = [];
try { sentUrls = JSON.parse(fs.readFileSync(SENT_FILE, 'utf8')); } catch (e) { sentUrls = []; }
const sentSet = new Set(sentUrls);

const { execSync } = require('child_process');
let xmlContent;
try {
  xmlContent = execSync(`curl -sL --max-time 20 "${FEED_URL}"`, { encoding: 'utf8', timeout: 25000 });
} catch (e) {
  console.error('获取 RSS 失败:', e.message);
  process.exit(1);
}

const items = [];
const itemRegex = /<item>[\s\S]*?<\/item>/g;
let match;
while ((match = itemRegex.exec(xmlContent)) !== null) {
  const itemXml = match[0];
  const titleMatch = itemXml.match(/<title><!\[CDATA\[([^\]]*)\]\]><\/title>/);
  const linkMatch = itemXml.match(/<link>([^<]*)<\/link>/);
  const pubDateMatch = itemXml.match(/<pubDate>([^<]*)<\/pubDate>/);
  if (titleMatch && linkMatch && pubDateMatch) {
    const pubDate = parsePubDate(pubDateMatch[1]);
    if (pubDate >= todayStartUTC && pubDate <= nowUTC) {
      items.push({ title: titleMatch[1].trim(), link: linkMatch[1].trim(), pubDate });
    }
  }
}

const newItems = items.filter(item => !sentSet.has(item.link));

if (newItems.length === 0) {
  console.log('没有符合条件的新文章。');
  process.exit(0);
}

newItems.sort((a, b) => new Date(b.pubDate) - new Date(a.pubDate));

const dateStr = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
const hhStr = toBeijingHH(now);

const allSentUrls = [];

const msgFile = path.join(process.env.HOME, '.openclaw', 'rss-msg-batch-0.txt');
let msg = `🦞 RSS 日报\n\n📅 ${dateStr} ⏰ 更新于 ${hhStr}\n\n━━━━━━━━━━━━━━━━━━━━━━\n\n`;

for (let i = 0; i < newItems.length; i++) {
  const item = newItems[i];
  const num = i + 1;
  const domain = getDomain(item.link);
  msg += `${num}. 【${item.title}】\n`;
  msg += `来源：${domain}\n`;
  msg += `🔗 ${item.link}\n`;
  msg += `💡 要点：待 AI 总结...\n`;
  msg += `\n━━━━━━━━━━━━━━━━━━━━━━\n\n`;
  allSentUrls.push(item.link);
}

msg += `共 ${newItems.length} 篇新文章`;

fs.writeFileSync(msgFile, msg, 'utf8');
console.log(`消息已写入 ${msgFile}`);

// 保存已发送列表
const newSent = [...sentSet, ...allSentUrls];
fs.writeFileSync(SENT_FILE, JSON.stringify(newSent, null, 2), 'utf8');
console.log(`已发送 ${allSentUrls.length} 篇新文章，已更新 ${SENT_FILE}`);

// 输出 JSON 摘要供外部工具处理
const articles = newItems.map(item => ({
  title: item.title,
  link: item.link,
  domain: getDomain(item.link)
}));
console.log('ARTICLES_JSON=' + JSON.stringify(articles));
