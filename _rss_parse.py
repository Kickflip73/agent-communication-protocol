import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import json

sent_path = '/root/.openclaw/rss-sent.json'
try:
    with open(sent_path, 'r') as f:
        sent_urls = json.load(f)
except Exception:
    sent_urls = []
sent_set = set(sent_urls)

url = 'https://thinkpeace.github.io/rss-cache/feeds/fulltext-72h.xml'
with urllib.request.urlopen(url, timeout=30) as resp:
    xml_data = resp.read()

root = ET.fromstring(xml_data)

tz_sh = timezone(timedelta(hours=8))
today_start = datetime(2026, 8, 30, 0, 0, 0, tzinfo=tz_sh)
now = datetime.now(tz_sh)

articles = []
for item in root.findall('.//item'):
    title = item.findtext('title', default='').strip()
    link = item.findtext('link', default='').strip()
    pub_date_str = item.findtext('pubDate', default='').strip()
    category = item.findtext('category', default='').strip()
    desc = item.findtext('description', default='').strip()
    
    try:
        dt = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S %z')
    except Exception:
        continue
    
    dt_sh = dt.astimezone(tz_sh)
    
    if today_start <= dt_sh <= now and link not in sent_set:
        articles.append({
            'title': title,
            'link': link,
            'pubDate': dt_sh,
            'category': category,
            'description': desc
        })

print(f"MATCHED:{len(articles)}")
for a in articles:
    print(f"ARTICLE|{a['pubDate'].isoformat()}|{a['title']}|{a['link']}|{a['category']}")
