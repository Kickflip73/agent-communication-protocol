#!/usr/bin/env python3
import json
import re

# Load sent URLs
with open('/root/.openclaw/rss-sent.json', 'r') as f:
    sent_urls = set(json.load(f))

# The RSS output text
rss_text = open('/root/.openclaw/workspace/rss_raw.txt', 'r').read()

# Parse articles
articles = []
pattern = r'\d+\.\s+(.+?)\n\s+(https?://\S+)\n\s+Published:\s+(\d+/\d+/\d+)'
for match in re.finditer(pattern, rss_text):
    title = match.group(1).strip()
    url = match.group(2).strip()
    date_str = match.group(3).strip()
    
    # Filter: only today (6/29/2026)
    if date_str != '6/29/2026':
        continue
    
    # Filter: not already sent
    if url in sent_urls:
        continue
    
    articles.append({'title': title, 'url': url, 'date': date_str})

# Categorize: high-value tech/AI articles vs 36kr financial news briefs
high_value = []
financial_briefs = []

for a in articles:
    url = a['url']
    title = a['title']
    # 36kr newsflashes are typically low-value financial blurbs
    if '36kr.com/newsflashes' in url:
        financial_briefs.append(a)
    else:
        high_value.append(a)

print(f"=== HIGH VALUE ARTICLES ({len(high_value)}) ===")
for i, a in enumerate(high_value, 1):
    print(f"{i}. {a['title']}")
    print(f"   {a['url']}")

print(f"\n=== 36KR FINANCIAL BRIEFS ({len(financial_briefs)}) ===")
for i, a in enumerate(financial_briefs, 1):
    print(f"{i}. {a['title']}")
    print(f"   {a['url']}")

# Save all new article URLs for later
all_new_urls = [a['url'] for a in articles]
with open('/root/.openclaw/workspace/rss_new_urls.json', 'w') as f:
    json.dump(all_new_urls, f, indent=2)

print(f"\nTotal new articles: {len(articles)}")
print(f"High-value: {len(high_value)}, Financial briefs: {len(financial_briefs)}")
