# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A daily scraper for tech/AI events on Luma (lu.ma) using Luma's undocumented internal JSON endpoint (`api.luma.com/discover/get-paginated-events`). No official API key required. The script runs once per day via cron or GitHub Actions.

## Commands

Once implemented, the expected entry point will be:

```bash
python scraper.py          # run a single scrape session
python scraper.py --dry-run  # run without writing output files (validate connectivity)
```

## Architecture

**Stack**: Pure Python (stdlib only — no external dependencies unless strictly necessary, per RNF-4). No framework, no database.

**Data flow per run:**
1. For each `(category, city)` pair from config, call the paginated Luma endpoint.
2. Parse events, deduplicate against `seen_events.json`.
3. Append new events to `events_master.csv` and write `new_events_<YYYY-MM-DD>.csv`.
4. Update `seen_events.json` with newly seen `api_id`s.

**State files (all local, gitignored):**
- `seen_events.json` — deduplication index keyed by `api_id`
- `events_master.csv` — append-only master history
- `new_events_<YYYY-MM-DD>.csv` — today's new events only

**Configuration (top of script or `config.py`):**
- Categories: `["tech", "ai"]`
- Cities: list of `{name, lat, lon}` dicts — at least 5 cities (requirement RF-10)
- Max pages per request series, delay between requests

## Key Implementation Constraints

- **Deduplication key**: `api_id` field from Luma's response (RF-3). Never re-report an event seen in a prior run.
- **Pagination**: loop until no `next_cursor` or until a safety page limit is hit (RF-2).
- **Resilience**: wrap each HTTP request in retry logic with exponential backoff. A single field parse failure must log and continue — never abort the full run (RNF-3, RF-8).
- **Rate limiting**: random sleep between requests (RNF-2). No parallel requests.
- **`first_seen` field**: every event written to CSV must include the date it was first detected (RNF-6).
- **Minimum CSV fields**: `name`, `url`, `start_date`, `city`, `category`, `first_seen` (RF-5).

## Scheduling

GitHub Actions workflow (`.github/workflows/scrape.yml`) scheduled with `cron: '0 8 * * *'`. State files must be committed back to the repo or persisted via Actions cache/artifact so deduplication survives across runs.

## Source Endpoint Notes

Luma's undocumented endpoint behavior:
- Accepts `slug` (category), `latitude`, `longitude`, and `pagination_cursor` query params.
- Returns a JSON payload with an `events` array and optional `next_cursor`.
- Schema may change without notice — log raw response on unexpected shapes (Risk table in PRD section 10).
