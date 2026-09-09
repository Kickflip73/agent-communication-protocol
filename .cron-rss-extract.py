import json, re, sys
from datetime import datetime, timezone, timedelta

# Read sent URLs
with open('/root/.openclaw/workspace/.cron-rss-sent.json') as f:
    sent = set(json.load(f))

sh = timezone(timedelta(hours=8))
today_start = datetime.now(sh).replace(hour=0, minute=0, second=0, microsecond=0)
now = datetime.now(sh)

raw = sys.stdin.read()

# Strip security wrapper if present
if '<<<EXTERNAL_UNTRUSTED_CONTENT' in raw:
    parts = raw.split('---', 1)
    if len(parts) > 1:
        raw = parts[1]
    # Remove trailing END tag
    raw = re.sub(r'<<<END_EXTERNAL_UNTRUSTED_CONTENT[^>]*>>>', '', raw)

# Parse RSS XML items
items = []
for item_match in re.finditer(r'<item>(.*?)</item>', raw, re.DOTALL):
    item = item_match.group(1)
    title = re.search(r'<title>(.*?)</title>', item, re.DOTALL)
    link = re.search(r'<link>(.*?)</link>', item, re.DOTALL)
    pub = re.search(r'<pubDate>(.*?)</pubDate>', item, re.DOTALL)
    desc = re.search(r'<description>(.*?)<', item, re.DOTALL)
    cat = re.search(r'<category>(.*?)</category>', item, re.DOTALL)
    content = re.search(r'<content:encoded><!\[CDATA\[(.*?)\]\]></content:encoded>', item, re.DOTALL)

    if not title or not link:
        continue

    title = title.group(1).strip()
    url = link.group(1).strip()
    pub_str = pub.group(1).strip() if pub else ''
    desc_text = desc.group(1).strip() if desc else ''
    # Unescape XML entities in description
    desc_text = desc_text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')
    source = cat.group(1).strip() if cat else re.sub(r'^https?://(www\.)?', '', url).split('/')[0]

    # Parse pubDate
    try:
        pub_dt = datetime.strptime(pub_str, '%a, %d %b %Y %H:%M:%S %z')
        pub_dt = pub_dt.astimezone(sh)
    except:
        continue

    if url in sent:
        continue

    if today_start <= pub_dt <= now:
        # Extract content text
        content_text = ''
        if content:
            content_text = content.group(1)
            # Strip HTML tags
            content_text = re.sub(r'<script[^>]*>.*?</script>', '', content_text, flags=re.DOTALL)
            content_text = re.sub(r'<style[^>]*>.*?</style>', '', content_text, flags=re.DOTALL)
            content_text = re.sub(r'<[^>]+>', ' ', content_text)
            content_text = re.sub(r'\s+', ' ', content_text).strip()

        items.append({
            'title': title,
            'url': url,
            'source': source,
            'pubDate': pub_str,
            'description': desc_text,
            'content': content_text[:800]
        })

print(json.dumps(items, ensure_ascii=False, indent=2))
print(f'\nTotal new articles today (not sent): {len(items)}', file=sys.stderr)
