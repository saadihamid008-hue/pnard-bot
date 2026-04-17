"""ADB scraper — two RSS feeds verified live April 2026.

  - Global tender notices (filter for Pakistan in the code)
  - Pakistan-specific projects and documents (already filtered)
"""
import hashlib
import re
from xml.etree import ElementTree as ET

import requests

FEEDS = [
    # Global tender notices — we filter by country name in title/summary
    ("ADB Tenders", "https://www.adb.org/projects/tenders/rss", True),
    # Pakistan-specific projects (shows new approvals + document uploads, which
    # often precede procurement)
    ("ADB Pakistan Projects", "https://www.adb.org/projects/country/pak/rss", False),
]

PAKISTAN_PATTERNS = [
    re.compile(r"\bpakistan\b", re.I),
    re.compile(r"\bPAK\b"),   # ADB country code prefix
    re.compile(r"\bPK\b"),
]

TIMEOUT = 20
UA = "PNARD-Bot/1.0 (opportunity monitoring; contact via pnard.com)"


def scrape_adb() -> list[dict]:
    out: list[dict] = []
    for source, url, filter_pakistan in FEEDS:
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"[ADB] {source} fetch failed: {e}")
            continue
        try:
            root = ET.fromstring(r.content)
        except ET.ParseError as e:
            print(f"[ADB] {source} parse failed: {e}")
            continue
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = (item.findtext("description") or "").strip()
            pub = (item.findtext("pubDate") or "").strip()
            if not title or not link:
                continue
            if filter_pakistan:
                blob = f"{title} {desc}"
                if not any(p.search(blob) for p in PAKISTAN_PATTERNS):
                    continue
            lid = "adb:" + hashlib.sha1(link.encode("utf-8")).hexdigest()[:16]
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
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    return " ".join(text.split())
