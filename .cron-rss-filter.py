import json, re, sys
from datetime import datetime, timezone, timedelta

# Read sent URLs
with open('/root/.openclaw/workspace/.cron-rss-sent.json') as f:
    sent = set(json.load(f))

sh = timezone(timedelta(hours=8))
today_start = datetime.now(sh).replace(hour=0, minute=0, second=0, microsecond=0)
now = datetime.now(sh)

raw = sys.stdin.read()

# Parse the rss-viewer output
articles = []
current = None
for line in raw.split('\n'):
    line = line.rstrip()
    # Match article number like "1. Title"
    m = re.match(r'^\s*(\d+)\.\s+(.+)$', line)
    if m:
        if current:
            articles.append(current)
        current = {'title': m.group(2).strip(), 'url': '', 'date': '', 'source': ''}
        continue
    if current and line.startswith('   https://'):
        current['url'] = line.strip()
        current['source'] = re.sub(r'^https?://(www\.)?', '', current['url']).split('/')[0]
        continue
    if current and 'Published:' in line:
        current['date'] = line.split('Published:')[1].strip().split('  ')[0].strip()
        continue

if current:
    articles.append(current)

new_articles = []
for a in articles:
    url = a['url']
    if not url or url in sent:
        continue
    pub_str = a['date']
    if not pub_str:
        continue
    try:
        pub = datetime.strptime(pub_str, '%m/%d/%Y').replace(tzinfo=sh)
    except:
        continue
    if today_start <= pub <= now:
        new_articles.append(a)

print(json.dumps(new_articles, ensure_ascii=False, indent=2))
print(f'\nTotal new articles today (not sent): {len(new_articles)}', file=sys.stderr)
