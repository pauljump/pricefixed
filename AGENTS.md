# Driving pricefixed with an AI agent

This repo is built to be handed to an LLM (Claude, Codex, or any coding agent). This file is the instruction sheet. If you are an agent, read this first.

## What this repo does

It pulls apartment listings straight from landlord-direct feeds and writes them to a local SQLite database (`listings.db`), keeping a price-history snapshot on every pull. No dependencies, Python 3.9+ standard library only.

## The three commands

```bash
python3 scrape.py            # pull every registered source into ./listings.db
python3 scrape.py --list     # list available sources
python3 scrape.py --status   # per-source active counts
python3 scrape.py --source stuytown   # pull one source
```

## The data model

`listings.db` has three tables (full schema in `pricefixed/core.py`):

- **`listings`** — current inventory. One row per unit per source. Key columns: `source`, `source_id`, `address`, `unit_number`, `bedrooms`, `bathrooms`, `price`, `sqft`, `lease_terms` (JSON: `[{term, price}, ...]`), `neighborhood`, `borough`, `status` (`active`/`inactive`), `first_seen`, `last_seen`, `raw_json`.
- **`price_history`** — one snapshot per listing per pull day. Columns: `source`, `source_id`, `snapshot_date`, `price`, `lease_terms`, `status`. This is how you recover what a unit asked over time.
- **`pull_log`** — one row per source per pull: `pulled_at`, `listings_count`, `new_count`, `updated_count`.

## Common tasks, and how to do them

**"Find every 1-bed under $3,000 that dropped its price this week."**
Pull, then diff `price_history` for each `source_id` between the latest snapshot and one 7+ days earlier, filtered to `bedrooms=1 AND price < 3000` and a negative delta.

**"Keep the database fresh."**
Put `python3 scrape.py` on a cron (or a GitHub Action) daily. Each run appends to `price_history`, so the longer it runs, the more valuable the history becomes.

**"Add a new landlord."**
1. Find the landlord's own availability feed (their site's XHR call, an API, or a static JSON). Landlord-direct only, never a login-walled aggregator.
2. Create `pricefixed/adapters/<name>.py`: subclass `SourceAdapter`, set `name` and `description`, implement `pull()` to return a list of dicts using the fields in `pricefixed/core.py` (`LISTING_FIELDS`). Only `source_id` is required; everything else is best-effort.
3. Register it in `pricefixed/adapters/__init__.py`.
4. Test: `python3 scrape.py --source <name>` should print a nonzero count.
See `CONTRIBUTING.md` and any existing adapter for the exact shape.

**"Check what is still working."**
`python3 healthcheck.py` runs every source and reports which are green and which broke. It exits nonzero if any feed is down, so it can drive an alert.

## The public record layer (`build_record.py`)

Separate from the live-listing feeds, `build_record.py` builds a canonical record of every NYC building from NYC Open Data (Socrata). Same shape as `scrape.py`: `--list`, `--status`, `--source <name>`, plus `--limit N` to sample instead of pulling all of NYC.

- Output db: `record.db`, two tables. `buildings` (one row per BBL: address, year_built, units, building_class, owner_name, rollup counts) and `building_events` (the history timeline: `bbl, event_type, event_date, source, amount, party, detail`).
- Sources live in `pricefixed/record/`, each a `RecordSource` subclass (see `pricefixed/record/core.py`), registered in `pricefixed/record/__init__.py`. Adding one mirrors adding an adapter: find the NYC Open Data dataset id, verify its real field keys by pulling `--limit 2`, map to the schema, register.
- This layer is public record only. It never contains rent data — that is out of scope here by design.

## Rules of the road

- **Landlord-direct only.** Targets are public availability feeds landlords publish to lease their units. Do not add sources that require an account, defeat an access control, or belong to an aggregator (Zillow, StreetEasy, RentHop). That is both the ethic and the legal line.
- **Be gentle.** Honor rate limits. The framework retries with backoff already. Do not parallel-hammer a source.
- **No new dependencies.** Standard library only. If a source needs a headless browser to discover its API, do that discovery yourself and ship an adapter that uses plain `fetch()` at runtime.
- **Keep `lease_terms` structured.** When a source exposes per-lease-length pricing, store it as JSON `[{term, price}]`. That column is the most valuable thing in the database.
