import json

with open('/root/.openclaw/rss-sent.json', 'r') as f:
    sent = json.load(f)

new_urls = [
    "https://shkspr.mobi/blog/2026/07/book-review-dungeon-crawler-carl-by-matt-dinniman/",
    "https://www.troyhunt.com/weekly-update-514/",
    "https://simonwillison.net/2026/Jul/25/ruff/#atom-everything",
    "https://ludic.mataroa.blog/blog/ai-mania-is-eviscerating-global-decision-making/",
    "https://digital-markets-act.ec.europa.eu/commission-fines-google-eur890-million-breaches-digital-markets-act-2026-07-23_en",
    "https://serpapi.com/blog/google-v-serpapi-the-court-granted-our-motion-to-dismiss/",
    "https://www.apple.com/newsroom/2026/07/apple-maps-to-power-navigation-experience-for-ford-uev-platform/",
    "https://www.nytimes.com/2026/07/24/well/measles-record-united-states-numbers.html?unlocked_article_code=1.0VA.4jBf.vqAYN4Bwu807"
]

combined = list(dict.fromkeys(sent + new_urls))

with open('/root/.openclaw/rss-sent.json', 'w') as f:
    json.dump(combined, f, indent=2)

print(f"Added {len(new_urls)} URLs. Total sent: {len(combined)} (was {len(sent)})")
