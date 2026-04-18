"""PNARD opportunity bot — runs hourly via GitHub Actions, posts new matches to Telegram.

Filters for:
  1. A clear funding signal (call for proposals, EOI, RFP, consultancy, etc.)
  2. Relevance to PNARD's lane (Pakistan agriculture, climate, gender, etc.)
  3. Deadline not yet passed (based on dates parsed from the listing text)
"""
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests

from scrapers.reliefweb import scrape_reliefweb
from scrapers.adb import scrape_adb
from scrapers.worldbank import scrape_worldbank
from scrapers.undp import scrape_undp

ROOT = Path(__file__).parent
SEEN_FILE = ROOT / "seen.json"

# ---------------------------------------------------------------------------
# Scoring: two-tier
#   FUNDING_SIGNALS — must have at least one, or the listing is dropped
#   CONTEXT_KEYWORDS — boost the score for PNARD-relevant topics
# ---------------------------------------------------------------------------

FUNDING_SIGNALS = {
    "call for proposal": 10, "call for proposals": 10,
    "call for application": 10, "call for applications": 10,
    "call for expression": 10, "expression of interest": 10, "eoi": 8,
    "request for proposal": 10, "rfp": 8, "rfp-": 8, "-rfp": 8,
    "request for quotation": 8, "rfq": 6, "rfq-": 8, "-rfq": 8,
    "invitation to bid": 10, "invitation to tender": 10,
    "itb-": 8, "-itb-": 8,
    "ic-20": 7,   # UNDP individual contractor code (IC-2026-XXX)
    "terms of reference": 8, "tor ": 5,
    "tender notice": 10, "tender for": 8,
    "procurement notice": 8, "procurement of": 6,
    "consultancy": 7, "consultant": 5,
    "call for consultant": 10,
    "apply by": 6, "application deadline": 8,
    "deadline for": 5, "closing date": 5,
    "seeking proposals": 10, "proposals are invited": 10,
    "hiring": 4, "recruiting": 4,
    "grant opportunity": 8, "funding opportunity": 8,
    "scholarship": 3, "fellowship": 4,
}

CONTEXT_KEYWORDS = {
    "pakistan": 5, "regenerative": 5, "agroecolog": 5, "climate-smart": 4,
    "climate smart": 4, "soil health": 4, "smallholder": 4,
    "agriculture": 3, "agricultural": 3, "livestock": 3, "food system": 3,
    "food security": 3, "rural": 2, "farmer": 3, "horticulture": 3,
    "nutrition": 2, "climate adaptation": 4, "climate resilience": 4,
    "gender": 2, "women": 2,
    "sindh": 4, "punjab": 3, "balochistan": 3, "khyber": 3, "pakhtunkhwa": 3,
}

MIN_SCORE = 10

# Topics PNARD does not bid on. If any of these terms dominate the title,
# the listing is dropped even if it has funding signals.
IRRELEVANT_PATTERNS = [
    # Physical supply/procurement, not consulting work
    re.compile(r"\bsupply\s+(?:and\s+)?(?:installation|delivery|of)\b", re.I),
    re.compile(r"\bprocurement\s+and\s+supply\b", re.I),
    re.compile(r"\b(?:beautician|cosmetic|fashion|abaya|jewellery|sport|tool)\s+kits?\b", re.I),
    re.compile(r"\bconstruction\b.{0,30}\b(?:boreholes?|water\s+tower|housing|office|building)\b", re.I),
    re.compile(r"\b(?:catering|conference)\s+services?\b", re.I),
    re.compile(r"\bserver\s+equipment\b", re.I),
    re.compile(r"\b(?:stationery|vehicles?|fuel|uniforms?)\b", re.I),
    # Clearly off-country positions that still mention Pakistan somewhere
    re.compile(r"\b(?:afghanistan|iraq|syria|yemen|sudan|myanmar|ukraine)\s+(?:country\s+)?director\b", re.I),
]

# Countries that frequently appear in regional postings but aren't PNARD's scope.
# A listing is dropped if its title names one of these WITHOUT also naming Pakistan.
OFF_COUNTRY_IF_NO_PAKISTAN = re.compile(
    r"\b(afghanistan|iraq|syria|yemen|sudan|myanmar|ukraine|lebanon|somalia|"
    r"ethiopia|dr\s+congo|palestine|gaza|venezuela|haiti)\b", re.I,
)
PAKISTAN_MENTION = re.compile(r"\bpakistan\b", re.I)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()


# ---------------------------------------------------------------------------
# Deadline parsing
# ---------------------------------------------------------------------------

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

DEADLINE_CUES = re.compile(
    r"(deadline|apply\s*by|applications?\s*close|closing\s*date|"
    r"submission\s*deadline|due\s*(?:by|date)|expires?|last\s*date|"
    r"no\s*later\s*than|before)\b[:\s]*",
    re.I,
)

DATE_PATTERNS = [
    # "30 April 2026" / "30 Apr 2026" / "30-April-2026"
    re.compile(r"(\d{1,2})[\s\-/]+(jan|january|feb|february|mar|march|apr|april|may|"
               r"jun|june|jul|july|aug|august|sep|sept|september|oct|october|"
               r"nov|november|dec|december)[\s\-/,]+(\d{4})", re.I),
    # "April 30, 2026" / "April 30 2026"
    re.compile(r"(jan|january|feb|february|mar|march|apr|april|may|"
               r"jun|june|jul|july|aug|august|sep|sept|september|oct|october|"
               r"nov|november|dec|december)[\s\-/]+(\d{1,2})[\s\-/,]+(\d{4})", re.I),
    # "2026-04-30" / "2026/04/30"
    re.compile(r"(\d{4})[\-/](\d{1,2})[\-/](\d{1,2})"),
    # "30/04/2026" / "30-04-2026"
    re.compile(r"(\d{1,2})[\-/](\d{1,2})[\-/](\d{4})"),
    # "05-Jan-26" / "30-Apr-26" — UNDP's format, 2-digit year
    re.compile(r"(\d{1,2})[\s\-/]+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[\s\-/,]+(\d{2})(?!\d)", re.I),
]


def parse_deadline(text: str):
    if not text:
        return None
    candidates = []
    for m in DEADLINE_CUES.finditer(text):
        window = text[m.end(): m.end() + 80]
        for pat in DATE_PATTERNS:
            dm = pat.search(window)
            if not dm:
                continue
            parsed = _date_from_match(dm, pat)
            if parsed:
                candidates.append(parsed)
                break
    if not candidates:
        return None
    today = date.today()
    future = [d for d in candidates if d >= today]
    return min(future) if future else max(candidates)


def _date_from_match(m, pat):
    groups = m.groups()
    try:
        if pat is DATE_PATTERNS[0]:
            day = int(groups[0]); month = MONTHS[groups[1].lower()]; year = int(groups[2])
        elif pat is DATE_PATTERNS[1]:
            month = MONTHS[groups[0].lower()]; day = int(groups[1]); year = int(groups[2])
        elif pat is DATE_PATTERNS[2]:
            year = int(groups[0]); month = int(groups[1]); day = int(groups[2])
        elif pat is DATE_PATTERNS[3]:
            day = int(groups[0]); month = int(groups[1]); year = int(groups[2])
        else:  # DATE_PATTERNS[4] — 2-digit year, assume 20xx
            day = int(groups[0]); month = MONTHS[groups[1].lower()]
            yy = int(groups[2])
            # Rough heuristic: 00-50 -> 2000-2050, 51-99 -> 1951-1999
            year = 2000 + yy if yy <= 50 else 1900 + yy
        if not (1 <= month <= 12 and 1 <= day <= 31 and 2020 <= year <= 2035):
            return None
        return date(year, month, day)
    except (ValueError, KeyError):
        return None


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def load_seen():
    if not SEEN_FILE.exists():
        return set()
    try:
        with SEEN_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return set(data)
        if isinstance(data, dict):
            return set(data.keys())
        return set()
    except (json.JSONDecodeError, OSError) as e:
        print(f"[seen] Could not read {SEEN_FILE}: {e}. Starting fresh.", file=sys.stderr)
        return set()


def save_seen(seen):
    tmp = SEEN_FILE.with_suffix(".json.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(sorted(seen), f, indent=2)
        tmp.replace(SEEN_FILE)
    except OSError as e:
        print(f"[seen] Failed to save: {e}", file=sys.stderr)
        if tmp.exists():
            tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Scoring + filtering
# ---------------------------------------------------------------------------

def score_listing(listing):
    text = f"{listing.get('title','')} {listing.get('summary','')}".lower()
    funding_score = sum(w for kw, w in FUNDING_SIGNALS.items() if kw in text)
    if funding_score == 0:
        return 0
    context_score = sum(w for kw, w in CONTEXT_KEYWORDS.items() if kw in text)
    return funding_score + context_score


def is_expired(listing):
    text = f"{listing.get('title','')} {listing.get('summary','')}"
    deadline = parse_deadline(text)
    if deadline is None:
        return False
    return deadline < date.today()


def is_irrelevant(listing) -> bool:
    """True if the listing is obviously not PNARD work (physical procurement,
    off-country jobs, etc.)"""
    title = listing.get("title", "")
    for pat in IRRELEVANT_PATTERNS:
        if pat.search(title):
            return True
    # Off-country posting that doesn't also mention Pakistan
    if OFF_COUNTRY_IF_NO_PAKISTAN.search(title) and not PAKISTAN_MENTION.search(title):
        return True
    return False


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def format_message(listing, score):
    title = listing.get("title", "Untitled").strip()
    source = listing.get("source", "?")
    url = listing.get("url", "")
    date_str = listing.get("date", "")
    summary = (listing.get("summary") or "").strip()
    if len(summary) > 300:
        summary = summary[:297] + "…"

    deadline = parse_deadline(f"{title} {summary}")
    deadline_line = f"⏰ Deadline: {deadline.isoformat()}" if deadline else ""

    lines = [
        f"🎯 {title}",
        f"{source} · score {score}" + (f" · {date_str}" if date_str else ""),
    ]
    if deadline_line:
        lines.append(deadline_line)
    if summary:
        lines.append("")
        lines.append(summary)
    if url:
        lines.append("")
        lines.append(url)
    return "\n".join(lines)


def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "disable_web_page_preview": False,
            },
            timeout=15,
        )
        if r.status_code != 200:
            print(f"[telegram] {r.status_code}: {r.text[:200]}", file=sys.stderr)
            return False
        return True
    except requests.RequestException as e:
        print(f"[telegram] request failed: {e}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    seen = load_seen()
    print(f"[seen] loaded {len(seen)} known listing IDs")

    all_listings = []
    for name, scraper in [
        ("ReliefWeb", scrape_reliefweb),
        ("ADB", scrape_adb),
        ("World Bank", scrape_worldbank),
        ("UNDP", scrape_undp),
    ]:
        try:
            got = scraper()
            print(f"[{name}] {len(got)} listings")
            all_listings.extend(got)
        except Exception as e:
            print(f"[{name}] FAILED: {e}", file=sys.stderr)

    new_matches = []
    new_ids = set()
    dropped_expired = 0
    dropped_no_funding = 0
    dropped_irrelevant = 0

    # Sources like "World Bank" are project records, not open calls. We track
    # them in seen.json but never alert on them — they're pipeline intel you
    # can check manually, not things to bid on today.
    NON_ALERTING_SOURCES = {"World Bank"}

    for listing in all_listings:
        lid = listing.get("id")
        if not lid:
            continue
        new_ids.add(lid)
        if lid in seen:
            continue
        if listing.get("source") in NON_ALERTING_SOURCES:
            continue
        if is_irrelevant(listing):
            dropped_irrelevant += 1
            continue
        score = score_listing(listing)
        if score == 0:
            dropped_no_funding += 1
            continue
        if score < MIN_SCORE:
            continue
        if is_expired(listing):
            dropped_expired += 1
            continue
        new_matches.append((listing, score))

    new_matches.sort(key=lambda x: x[1], reverse=True)
    print(f"[filter] dropped {dropped_no_funding} (no funding signal), "
          f"{dropped_irrelevant} (irrelevant), "
          f"{dropped_expired} (expired deadline)")
    print(f"[match] {len(new_matches)} new listings above score {MIN_SCORE}")

    seen.update(new_ids)
    save_seen(seen)
    print(f"[seen] saved {len(seen)} IDs")

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[telegram] no credentials set — dry run, would have sent:")
        for listing, score in new_matches[:20]:
            print(f"  [{score}] {listing.get('source')}: {listing.get('title','')[:90]}")
        return 0

    sent = 0
    for listing, score in new_matches:
        msg = format_message(listing, score)
        if send_telegram(msg):
            sent += 1
            time.sleep(1.2)
    print(f"[telegram] sent {sent}/{len(new_matches)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
