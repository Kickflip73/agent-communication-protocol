import xml.etree.ElementTree as ET
import json, re
from datetime import datetime, timezone, timedelta

root = ET.parse('/tmp/rss.xml').getroot()
ns = {'content': 'http://purl.org/rss/1.0/modules/content/'}

items = root.findall('.//item')
articles = []
for item in items:
    title = item.findtext('title', '')
    link = item.findtext('link', '')
    pub_str = item.findtext('pubDate', '')
    desc = item.findtext('description', '')
    cat = item.findtext('category', '')
    content = item.find('content:encoded', ns)
    content_text = (content.text or '') if content is not None else ''
    try:
        dt = datetime.strptime(pub_str, '%a, %d %b %Y %H:%M:%S %z')
    except:
        dt = datetime.now(timezone.utc)
    articles.append({
        'title': title,
        'url': link,
        'pubDate': pub_str,
        'pubTimestamp': dt.isoformat(),
        'source': cat,
        'description': desc,
        'content': content_text[:3000]
    })

sent = set()
try:
    with open('/root/.openclaw/rss-sent.json') as f:
        sent = set(json.load(f))
except:
    pass

today_start = datetime(2026, 7, 25, 16, 0, 0, tzinfo=timezone.utc)
now = datetime(2026, 7, 26, 13, 48, 0, tzinfo=timezone.utc)

new_articles = []
for a in articles:
    a_dt = datetime.fromisoformat(a['pubTimestamp'])
    if today_start <= a_dt <= now and a['url'] not in sent:
        new_articles.append(a)

new_articles.sort(key=lambda x: x['pubTimestamp'], reverse=True)

print(f'Total articles: {len(articles)}')
print(f'New articles today: {len(new_articles)}')
for a in new_articles[:30]:
    print(f"- {a['title']} | {a['url']} | {a['pubDate']} | {a['source']}")

with open('/tmp/new-articles.json', 'w') as f:
    json.dump(new_articles, f, indent=2)
