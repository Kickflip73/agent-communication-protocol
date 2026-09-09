import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import json

# Parse the RSS feed
tree = ET.parse('/root/.openclaw/workspace/feed.xml')
root = tree.getroot()

# Get today's date in Shanghai (UTC+8)
now = datetime.now(timezone(timedelta(hours=8)))
today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
today_start_utc = today_start.astimezone(timezone.utc)
now_utc = now.astimezone(timezone.utc)

# Read sent URLs
sent = set()
try:
    with open('/root/.openclaw/rss-sent.json', 'r') as f:
        sent = set(json.load(f))
except:
    pass

print(f"Now Shanghai: {now}")
print(f"Today start UTC: {today_start_utc}")
print(f"Now UTC: {now_utc}")
print(f"Sent count: {len(sent)}")

articles = []
for item in root.findall('.//item'):
    title = item.find('title').text or ''
    link = item.find('link').text or ''
    pub_date_el = item.find('pubDate')
    pub_date_str = pub_date_el.text if pub_date_el is not None else ''
    desc_el = item.find('description')
    desc = desc_el.text if desc_el is not None else ''
    
    # Parse pubDate
    try:
        dt = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S %z')
    except:
        try:
            dt = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S %Z')
            dt = dt.replace(tzinfo=timezone.utc)
        except:
            continue
    
    # Check if in today's range
    if today_start_utc <= dt <= now_utc:
        if link not in sent:
            # Extract source from description
            source = desc.split(']')[0].replace('[', '') if '[' in desc else link.split('/')[2]
            articles.append({
                'title': title,
                'link': link,
                'pubDate': pub_date_str,
                'source': source,
                'description': desc
            })

print(f"\nNew articles today: {len(articles)}")
for i, a in enumerate(articles):
    print(f"{i+1}. {a['title']}")
    print(f"   {a['link']}")
    print(f"   {a['pubDate']}")
    print()

# Save filtered articles for processing
import json
with open('/root/.openclaw/workspace/articles_today.json', 'w') as f:
    json.dump(articles, f, indent=2)
