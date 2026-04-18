"""UNDP procurement notices scraper — RDF/RSS feed verified live April 2026.

Global feed includes ALL UNDP countries. We filter by country code or the
keyword "PAKISTAN" in the title (which UNDP appends to every item as
"... - PAKISTAN"). UNDP also has a structured deadline field which we use
for reliable expiration filtering.
"""
import hashlib
import re
import time
from datetime import date, datetime
from xml.etree import ElementTree as ET

import requests

# Global feed — returns all countries. We filter for Pakistan in code.
FEED_URL = "https://procurement-notices.undp.org/rss_feeds/rss.xml"

# Namespaces used in the RDF feed
NS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rss": "http://purl.org/rss/1.0/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "undp": "http://procurement-notices.undp.org/rss_feed/spec/",
}

PAKISTAN_PATTERN = re.compile(r"\bpakistan\b", re.I)

TIMEOUT = 25
UA = "PNARD-Bot/1.0 (opportunity monitoring; contact via pnard.com)"
MAX_RETRIES = 3
RETRY_DELAY = 3


def _fetch_with_retry(url: str):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
        except requests.RequestException as e:
            if attempt == MAX_RETRIES:
                raise
            print(f"[UNDP] attempt {attempt} error: {e}, retrying...")
            time.sleep(RETRY_DELAY)
            continue
        if r.status_code == 202 or (r.status_code == 200 and len(r.content) < 500):
            if attempt == MAX_RETRIES:
                return None
            time.sleep(RETRY_DELAY)
            continue
        r.raise_for_status()
        return r.content
    return None


def scrape_undp() -> list[dict]:
    try:
        content = _fetch_with_retry(FEED_URL)
    except requests.RequestException as e:
        print(f"[UNDP] fetch failed: {e}")
        return []
    if not content:
        print("[UNDP] empty response after retries")
        return []

    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        print(f"[UNDP] parse failed: {e}")
        return []

    out: list[dict] = []
    # In RDF/RSS 1.0, items are <item> elements in the RSS namespace
    for item in root.findall("rss:item", NS):
        title = _text(item, "rss:title")
        if not title:
            continue
        # Pakistan filter — UNDP suffixes the country to every title
        country = _text(item, "undp:duty_station_cty") or ""
        blob = f"{title} {country}"
        if not PAKISTAN_PATTERN.search(blob):
            continue

        link = _text(item, "rss:link") or item.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about", "")
        desc = _text(item, "rss:description") or ""
        pub = _text(item, "dc:date") or ""
        deadline_raw = _text(item, "undp:deadline") or ""

        # If we already have a structured deadline, drop expired items here
        # rather than relying on the main bot's text-parsing heuristic.
        if deadline_raw:
            try:
                dl = datetime.fromisoformat(deadline_raw.replace("Z", "+00:00"))
                if dl.date() < date.today():
                    continue
                # Surface deadline in the summary so the bot's formatter picks it up
                if "deadline" not in desc.lower():
                    desc = f"Deadline: {dl.date().isoformat()}. {desc}"
            except ValueError:
                pass

        lid = "undp:" + hashlib.sha1(link.encode("utf-8")).hexdigest()[:16]
        out.append({
            "id": lid,
            "source": "UNDP",
            "title": title,
            "summary": desc,
            "url": link,
            "date": pub[:10] if pub else "",
        })
    return out


def _text(elem: ET.Element, path: str) -> str:
    child = elem.find(path, NS)
    return (child.text or "").strip() if child is not None and child.text else ""
