import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

url = 'https://thinkpeace.github.io/rss-cache/feeds/fulltext-72h.xml'
with urllib.request.urlopen(url, timeout=30) as resp:
    xml_data = resp.read()

root = ET.fromstring(xml_data)

tz_sh = timezone(timedelta(hours=8))
today_start = datetime(2026, 8, 30, 0, 0, 0, tzinfo=tz_sh)
now = datetime.now(tz_sh)

print(f"Now SH: {now.isoformat()}")
print(f"Today start SH: {today_start.isoformat()}")
print()

articles = []
for item in root.findall('.//item'):
    title = item.findtext('title', default='').strip()
    link = item.findtext('link', default='').strip()
    pub_date_str = item.findtext('pubDate', default='').strip()
    
    try:
        dt = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S %z')
    except Exception:
        continue
    
    dt_sh = dt.astimezone(tz_sh)
    articles.append((dt_sh, title, link))

# 按时间倒序
articles.sort(key=lambda x: x[0], reverse=True)

print(f"Total articles in feed: {len(articles)}")
print("\n--- Top 30 most recent articles ---")
for dt_sh, title, link in articles[:30]:
    in_range = today_start <= dt_sh <= now
    marker = "[IN RANGE]" if in_range else ""
    print(f"  {dt_sh.strftime('%Y-%m-%d %H:%M')} {marker} {title[:70]}")
