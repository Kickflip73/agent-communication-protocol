const fs = require("fs");
const { execSync } = require("child_process");

// 读取已发送列表
let sent = [];
try {
  sent = JSON.parse(fs.readFileSync("/root/.openclaw/rss-sent.json", "utf8"));
} catch(e) {}

// 获取今天文章
const todayStartUTC = "2026-09-06T16:00:00.000Z";
const nowUTC = "2026-09-07T08:31:00.000Z";

const sql = `SELECT title, link, published_at, content FROM articles WHERE published_at >= '${todayStartUTC}' AND published_at <= '${nowUTC}' AND content IS NOT NULL AND length(content) > 10 ORDER BY published_at DESC;`;
const cmd = `sqlite3 /root/.config/rss-viewer/feeds.db "${sql}"`;
const result = execSync(cmd, {encoding: "utf8"}).trim();

if (!result) {
  console.log(JSON.stringify([]));
  process.exit(0);
}

const rows = result.split("\n");
const articles = [];
for (const row of rows) {
  const parts = row.split("|");
  if (parts.length >= 4) {
    const link = parts[1];
    if (!sent.includes(link)) {
      articles.push({
        title: parts[0],
        link: link,
        published: parts[2],
        content: parts[3]
      });
    }
  }
}

console.log(JSON.stringify(articles, null, 2));
