# PNARD Opportunity Bot

An hourly Telegram bot that monitors three international development sources for Pakistan agriculture, climate, and rural-development opportunities and pings you when new matching listings appear.

Built for PNARD (Pro Nature Alliance R&D) to keep the bid pipeline warm without manual portal sweeps.

## What it watches

Three sources, all verified live as of April 2026:

1. **ReliefWeb** — three RSS feeds filtered to Pakistan: jobs (consultancies and staff roles), training (workshops and short assignments), and country updates (programme news that often flags upcoming calls).
2. **Asian Development Bank** — global tender notices (filtered to Pakistan in code) and Pakistan-specific project announcements.
3. **World Bank** — the public Projects API, pulling the 50 most recently approved Pakistan projects. New entries typically precede subcontracting windows by weeks to months.

Scrapers are independent. If one source breaks, the others keep running and the bot still delivers alerts.

## What it does

On each run:

1. Fetches fresh listings from all three sources.
2. Filters out anything already in `seen.json`.
3. Scores remaining listings against PNARD-specific keywords (regenerative, climate-smart, Pakistan, smallholder, sector-specific terms, and funding signals like tender, EOI, RFP, consultancy).
4. Saves all seen IDs to `seen.json` immediately, before Telegram delivery. If delivery fails or credentials are missing, the dedup state is still committed so you don't get spammed on the next run.
5. Sends the matches to your Telegram chat, ranked highest score first.

Listings are kept if they score 6 or above. On current feeds this is roughly 15-25% of incoming items.

## How it runs

A GitHub Actions workflow triggers the bot every hour and commits the updated `seen.json` back to the repo. No server, no database. Public repos get free unlimited minutes for scheduled jobs.

## Files

```
bot.py                       # orchestrator, scoring, dedup, Telegram
scrapers/reliefweb.py        # three RSS feeds
scrapers/adb.py              # two RSS feeds
scrapers/worldbank.py        # Projects API
seen.json                    # dedup state, committed by the bot
.github/workflows/bot.yml    # hourly cron
requirements.txt             # just `requests`
```

## Setup

See [SETUP.md](SETUP.md) for a start-to-finish walkthrough.

## Tuning

Two knobs in `bot.py`:

- `KEYWORDS` — the weighted keyword dictionary. Add terms, adjust weights.
- `MIN_SCORE` — the cutoff. Lowering it widens the funnel and adds noise; raising it narrows to high-confidence matches only.

Run locally with `python bot.py` (no credentials needed — it prints what it would have sent) to see how a change affects the match set before deploying.
