"""PNARD opportunity bot — runs hourly via GitHub Actions, posts new matches to Telegram."""
import json
import os
import sys
import time
from pathlib import Path

import requests

from scrapers.reliefweb import scrape_reliefweb
from scrapers.adb import scrape_adb
from scrapers.worldbank import scrape_worldbank

ROOT = Path(__file__).parent
SEEN_FILE = ROOT / "seen.json"

# Keywords that score a listing. Tuned for PNARD: regenerative ag in Pakistan,
# climate adaptation, gender-in-ag, livestock, smallholders, consulting/tender.
KEYWORDS = {
    # core mission — high weight
    "pakistan": 5, "regenerative": 5, "agroecolog": 5, "climate-smart": 4,
    "climate smart": 4, "soil health": 4, "smallholder": 4,
    # adjacent — medium weight
    "agriculture": 3, "livestock": 3, "food system": 3, "food security": 3,
    "rural": 2, "farmer": 3, "horticulture": 3, "nutrition": 2,
    "climate adaptation": 4, "climate resilience": 4, "gender": 2,
    "women": 2, "sindh": 4, "punjab": 3, "balochistan": 3, "khyber": 3,
    # funding signals — strong signal this is biddable
    "tender": 3, "consultancy": 3, "consultant": 3, "proposal": 2,
    "grant": 2, "call for": 3, "procurement": 3, "expression of interest": 4,
    "eoi": 3, "rfp": 3, "terms of reference": 3, "tor": 2,
}

MIN_SCORE = 6  # tuned on April 2026 data — gets ~15-25% of listings through

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()


def load_seen() -> set[str]:
    if not SEEN_FILE.exists():
        return set()
    try:
        with SEEN_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return set(data)
        # Back-compat: tolerate if someone saved it as a dict
        if isinstance(data, dict):
            return set(data.keys())
        return set()
    except (json.JSONDecodeError, OSError) as e:
        print(f"[seen] Could not read {SEEN_FILE}: {e}. Starting fresh.", file=sys.stderr)
        return set()


def save_seen(seen: set[str]) -> None:
    """Atomic write: write to temp file then rename. Prevents corruption if the
    process is killed mid-write (which was the old bug's failure mode)."""
    tmp = SEEN_FILE.with_suffix(".json.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(sorted(seen), f, indent=2)
        tmp.replace(SEEN_FILE)
    except OSError as e:
        print(f"[seen] Failed to save: {e}", file=sys.stderr)
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def score_listing(listing: dict) -> int:
    text = f"{listing.get('title','')} {listing.get('summary','')}".lower()
    return sum(weight for kw, weight in KEYWORDS.items() if kw in text)


def format_message(listing: dict, score: int) -> str:
    title = listing.get("title", "Untitled").strip()
    source = listing.get("source", "?")
    url = listing.get("url", "")
    date = listing.get("date", "")
    summary = (listing.get("summary") or "").strip()
    if len(summary) > 300:
        summary = summary[:297] + "…"

    lines = [
        f"🎯 {title}",
        f"{source} · score {score}" + (f" · {date}" if date else ""),
    ]
    if summary:
        lines.append("")
        lines.append(summary)
    if url:
        lines.append("")
        lines.append(url)
    return "\n".join(lines)


def _escape_md(text: str) -> str:
    # Telegram MarkdownV2 escapes — covers the characters that actually show up
    # in tender titles and RSS summaries.
    for ch in r"_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, "\\" + ch)
    return text


def send_telegram(message: str) -> bool:
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


def main() -> int:
    seen = load_seen()
    print(f"[seen] loaded {len(seen)} known listing IDs")

    all_listings: list[dict] = []
    for name, scraper in [
        ("ReliefWeb", scrape_reliefweb),
        ("ADB", scrape_adb),
        ("World Bank", scrape_worldbank),
    ]:
        try:
            got = scraper()
            print(f"[{name}] {len(got)} listings")
            all_listings.extend(got)
        except Exception as e:
            # One broken scraper should never take down the whole run.
            print(f"[{name}] FAILED: {e}", file=sys.stderr)

    # Filter to new + above score threshold
    new_matches: list[tuple[dict, int]] = []
    new_ids: set[str] = set()
    for listing in all_listings:
        lid = listing.get("id")
        if not lid:
            continue
        new_ids.add(lid)
        if lid in seen:
            continue
        score = score_listing(listing)
        if score >= MIN_SCORE:
            new_matches.append((listing, score))

    new_matches.sort(key=lambda x: x[1], reverse=True)
    print(f"[match] {len(new_matches)} new listings above score {MIN_SCORE}")

    # BUG FIX: persist seen BEFORE attempting Telegram delivery.
    # Old behaviour: save happened after successful send, so dry-runs (no token)
    # and failed sends caused the same listings to get re-matched next run.
    # New behaviour: once we've decided a listing is "seen", that decision is
    # committed to disk immediately. Delivery is best-effort.
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
            time.sleep(1.2)  # Telegram rate limit is ~30 msg/sec but be kind
        else:
            # Don't re-queue — listing is already in seen.json. Better to miss
            # one alert than to spam on every retry.
            pass
    print(f"[telegram] sent {sent}/{len(new_matches)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
