# Changelog

All notable changes to pricefixed are recorded here. This project follows
[Keep a Changelog](https://keepachangelog.com/) and dates are YYYY-MM-DD.

## [Unreleased]

Roadmap, in order (see the README for the full thesis):

- **More feeds.** Grow the NYC landlord-direct source set toward broad coverage. Platform
  adapters (RentCafe, MRI ProspectConnect, AppFolio) are the priority — one adapter, many landlords.
- **Published inventory.** A public dataset of what the feeds return over time, so nobody has to
  run the scrapers to get the history.
- **Algorithm transparency.** Public analysis of how landlord pricing software sets rent.

## [0.1.0] - 2026-07-11

First public release. A working tool from day one, with the shape to grow.

### Added
- Dependency-free scraping framework (`pricefixed/core.py`): HTTP with retries, a SQLite schema,
  price-history snapshots on every pull, and automatic inactive-listing tracking.
- CLI (`scrape.py`): `--list`, `--status`, `--source`.
- Live landlord-direct adapters for NYC.
- `healthcheck.py`: runs every feed, writes a live status table into the README, and exits
  nonzero when a feed breaks so it can drive an alert.
- `AGENTS.md` and `llms.txt`: instructions for driving the repo with an AI agent.
- `FEEDS.md`: registry of NYC apartment data sources, tiered by difficulty and by what each exposes.
