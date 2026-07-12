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

## [0.4.0] - 2026-07-11

Go upstream: the brokerage/IDX backdoor.

### Added
- **`corcoran` adapter** (`pricefixed/adapters/corcoran.py`) — current NYC rental listings
  from Corcoran's public backend API. A brokerage's search returns its own exclusives **plus**
  every listing syndicated to it via IDX/MLS (the REBNY RLS feed), so one adapter rides that
  syndication and reaches a large slice of the whole broker-listed market — no feed license
  required (~44 of every ~250 rows sampled are IDX, i.e. other brokers' listings).
- Pulls **active, on-market listings only** (`transactionTypes:["for-rent"]`, never a closed
  status), with a defensive `_is_active` filter so no sold/rented history can leak into the
  open dataset. The closed-rent history the same backend can serve is deliberately out of scope.
- The API key is Corcoran's own public web-app key; overridable via `CORCORAN_API_KEY` if it
  rotates (the healthcheck goes red when it does).
- **`FEEDS.md`** documents the brokerage/IDX method as a first-class tier, with a step-by-step
  guide to replicate it for Douglas Elliman (`core.api.elliman.com`) and Compass.

## [0.3.0] - 2026-07-11

Borough scoping — the record composes over one geography.

### Added
- **`build_record.py --boro`** (MN/BX/BK/QN/SI or 1–5): scopes every record source to a
  single borough, threaded through `RecordSource.run/pull` via new `core.py` helpers
  (`parse_boro`, `boro_clause`, `and_where`). This is what lets a *complete* record — owners
  AND violations AND evictions — land on the same BBLs, instead of thin all-NYC samples that
  never overlap. Most sources scope server-side on their native borough column (boroid /
  borough name / 2-letter / ACRIS numeric); the two address-only or flat-file sources
  (dob_complaints, rent_stabilization) scope by a BBL-prefix filter. Verified per source:
  every written BBL falls in the requested borough.

### Why it matters
- The Who-Owns-What portfolio rollup now shows a landlord's real combined violation / eviction /
  complaint record, because a one-borough build populates ownership and accountability on the
  same buildings.

## [0.2.0] - 2026-07-11

Phase 1: the record stops being a pile of feeds and starts composing into answers.

### Added
- **Who owns what** (`pricefixed/engine/portfolios.py`, `python build_record.py --portfolios`):
  clusters buildings into landlord portfolios by shared HPD-registered business address —
  unmasking single-purpose LLCs into one owner with a combined violation/eviction/complaint
  record. Buildings with no business address stay singletons rather than false-merging.
- **Dedupe / entity resolution** (`pricefixed/engine/dedupe.py`, `python scrape.py --dedupe`):
  collapses the same physical unit surfaced by multiple feeds into one canonical listing
  (prefers landlord-direct over the broker marketplace), writing `unit_dedup` + a
  `canonical_listings` view without touching the raw `listings` rows.
- **Rent-stabilization** record source (`pricefixed/record/rent_stabilization.py`): DHCR-derived
  stabilized-unit counts from the taxbills.nyc scrape, plus a J-51/421-a abatement proxy tier.
  Every row is tagged `rent_stab_year=2017` (the snapshot's vintage) and the source fails loud
  rather than fabricating a count if the upstream file moves.
- Scheduled **healthcheck CI** (`.github/workflows/healthcheck.yml`): runs the feed check daily
  (and on push / manual dispatch), commits the refreshed README status table, and shows a red
  run when a feed is down — with a status badge in the README.

### Changed
- Crosswalk address normalization lifted from 15 to 30 locked self-test cases: fixes the
  trailing-bare-unit miss ("4-75 48th Avenue 205" → "4-75 48 AVE") and folds SAINT→ST,
  FT→FORT, PLZ→PLAZA, verified against live PLUTO, without regressing any prior case.

### Fixed
- Circular import between `pricefixed.engine` and `pricefixed.record` that broke a fresh-process
  `python -m pricefixed.engine.crosswalk` (the documented demo entry point). The three record
  sources that use the crosswalk now import it lazily inside their methods.

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
