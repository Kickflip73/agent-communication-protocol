import json, sqlite3
from urllib.parse import urlparse
from datetime import datetime, timezone, timedelta

# 读取已发送列表
with open('/root/.openclaw/rss-sent.json', 'r') as f:
    sent_urls = set(json.load(f))

# 连接数据库
conn = sqlite3.connect('/root/.config/rss-viewer/feeds.db')
c = conn.cursor()

# 今天北京时间 0:00 UTC = 昨天 16:00 UTC
# 当前时间: 2026-09-01 22:05 北京时间 = 2026-09-01 14:05 UTC
today_start_utc = '2026-08-31T16:00:00Z'  # 北京时间 2026-09-01 00:00
current_utc = '2026-09-01T14:05:00Z'

c.execute(
    "SELECT title, link, published_at, summary, content FROM articles WHERE published_at >= ? AND published_at <= ? ORDER BY published_at DESC",
    (today_start_utc, current_utc)
)

articles = c.fetchall()
new_articles = []
for row in articles:
    title, link, published_at, summary, content = row
    if link not in sent_urls:
        new_articles.append(row)
        print(f"NEW: {title} | {link} | {published_at}")
    else:
        print(f"SENT: {title} | {link} | {published_at}")

print(f"\nTotal articles in range: {len(articles)}")
print(f"New articles: {len(new_articles)}")

conn.close()
