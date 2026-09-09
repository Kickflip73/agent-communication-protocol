#!/usr/bin/env python3
import json, urllib.request, re, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# 配置
FEED_URL = "https://thinkpeace.github.io/rss-cache/feeds/fulltext-72h.xml"
SENT_FILE = "/root/.openclaw/rss-sent.json"
TZ = timezone(datetime.now(timezone.utc).astimezone().utcoffset())

# 今天 0:00
now = datetime.now(TZ)
today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

# 读取已发送列表
try:
    with open(SENT_FILE, "r") as f:
        sent = set(json.load(f))
except:
    sent = set()

# 解析 RSS
def parse_rss_date(text):
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(TZ)
    except:
        return None

# 下载 RSS
req = urllib.request.Request(FEED_URL, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=30) as resp:
    xml = resp.read().decode("utf-8")

root = ET.fromstring(xml)

# 处理命名空间
ns = {
    "atom": "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/"
}

items = root.findall(".//item") or root.findall(".//atom:entry", ns)

articles = []
for item in items:
    def get(tag, nsmap=None):
        el = item.find(tag, nsmap or {})
        return (el.text or "").strip() if el is not None else ""
    
    title = get("title") or get("atom:title", ns)
    link = get("link") or get("atom:link", ns)
    pub = get("pubDate") or get("dc:date", ns) or get("atom:published", ns)
    
    if not link:
        for l in item.findall("link"):
            link = l.get("href", "")
            if link: break
    
    dt = parse_rss_date(pub) if pub else None
    if dt and today_start <= dt <= now:
        if link not in sent:
            articles.append({"title": title, "link": link, "date": dt})

print(f"articles={json.dumps(articles, ensure_ascii=False, default=str)}")
