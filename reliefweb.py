"""ReliefWeb scraper — uses the public RSS feeds that were verified live April 2026.

Three feeds:
  - jobs filtered to Pakistan (consultancies + staff postings)
  - training filtered to Pakistan (workshops, short-term assignments)
  - updates for Pakistan (country code C189) — programme news that flags
    upcoming calls
"""
import hashlib
from xml.etree import ElementTree as ET

import requests

FEEDS = [
    ("ReliefWeb Jobs", "https://reliefweb.int/jobs/rss.xml?search=pakistan"),
    ("ReliefWeb Training", "https://reliefweb.int/training/rss.xml?search=pakistan"),
    ("ReliefWeb Updates", "https://reliefweb.int/updates/rss.xml?search=pakistan"),
]

TIMEOUT = 20
UA = "PNARD-Bot/1.0 (opportunity monitoring; contact via pnard.com)"


def scrape_reliefweb() -> list[dict]:
    out: list[dict] = []
    for source, url in FEEDS:
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"[ReliefWeb] {source} fetch failed: {e}")
            continue
        try:
            root = ET.fromstring(r.content)
        except ET.ParseError as e:
            print(f"[ReliefWeb] {source} parse failed: {e}")
            continue
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = (item.findtext("description") or "").strip()
            pub = (item.findtext("pubDate") or "").strip()
            if not title or not link:
                continue
            lid = "rw:" + hashlib.sha1(link.encode("utf-8")).hexdigest()[:16]
            out.append({
                "id": lid,
                "source": source,
                "title": title,
                "summary": _strip_html(desc),
                "url": link,
                "date": pub,
            })
    return out


def _strip_html(text: str) -> str:
    # Lightweight — ReliefWeb descriptions have <p> and entities
    import re
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return " ".join(text.split())
