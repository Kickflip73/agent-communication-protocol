const fs = require('fs');
const sqlite3 = require('sqlite3').verbose();

// 读取已发送列表
let sentUrls = [];
try {
  sentUrls = JSON.parse(fs.readFileSync('/root/.openclaw/rss-sent.json', 'utf8'));
} catch(e) {
  sentUrls = [];
}
const sentSet = new Set(sentUrls);

// 时间窗口：今天 0:00 到当前时间 (Asia/Shanghai)
// Asia/Shanghai = UTC+8
// 今天 0:00 CST = 昨天 16:00 UTC
const now = new Date('2026-09-05T06:10:00Z'); // UTC now
const todayStart = new Date('2026-09-04T16:00:00Z'); // 2026-09-05 00:00 CST

console.log('Today start (UTC):', todayStart.toISOString());
console.log('Now (UTC):', now.toISOString());

const db = new sqlite3.Database('/root/.config/rss-viewer/feeds.db');

db.all(`SELECT title, link, published_at FROM articles ORDER BY published_at DESC`, [], (err, rows) => {
  if (err) {
    console.error(err);
    process.exit(1);
  }

  // 找出批量抓取的时间戳（大量文章在同一秒内）
  const timeCounts = {};
  rows.forEach(r => {
    const sec = r.published_at ? r.published_at.substring(0, 19) : '';
    timeCounts[sec] = (timeCounts[sec] || 0) + 1;
  });

  // 找出数量最多的那个秒级时间戳（应该是批量导入时间）
  let maxCount = 0;
  let batchTime = '';
  Object.entries(timeCounts).forEach(([t, c]) => {
    if (c > maxCount) {
      maxCount = c;
      batchTime = t;
    }
  });
  console.log('Batch import time:', batchTime, 'count:', maxCount);

  // 筛选：在时间内、未发送、不是批量导入的
  const candidates = rows.filter(r => {
    if (!r.published_at) return false;
    const pub = new Date(r.published_at);
    const sec = r.published_at.substring(0, 19);
    // 排除批量导入的文章
    if (sec === batchTime && maxCount > 10) return false;
    // 在时间窗口内
    if (pub < todayStart || pub > now) return false;
    // 未发送
    if (sentSet.has(r.link)) return false;
    return true;
  });

  console.log('New articles found:', candidates.length);
  candidates.forEach(c => {
    console.log(`- [${c.published_at}] ${c.title}`);
    console.log(`  ${c.link}`);
  });

  db.close();
});
