# pricefixed

[![feed status](https://github.com/pauljump/pricefixed/actions/workflows/healthcheck.yml/badge.svg)](https://github.com/pauljump/pricefixed/actions/workflows/healthcheck.yml) · **launch page: [pricefixed.polyfeeds.dev](https://pricefixed.polyfeeds.dev)**

**Open tools to pull every apartment's price and history out of the walled gardens, and a standardized public record of every NYC building. Point Claude or Codex at them and build.**

The rent number on your lease was not set by a person. It was set by software. Landlords across the country feed their vacancies into shared pricing algorithms like RealPage's YieldStar, and those algorithms quietly raise rents in lockstep across competitors. The Department of Justice sued over it and called it what it is: price-fixing.

You cannot audit an algorithm without the data it feeds on, and almost none of that data is public or standardized. So that is where this starts: pulling it into the open, owned by no one, for anyone to build on. To be clear about what this is today: it is the data layer, not the detector. Exposing the pricing algorithm itself is the destination (see the roadmap below), not a claim about what ships today.

`pricefixed` starts with the hard part every real-estate project starts with: getting the data. It gives those tools away.

---

## The idea

The data is the wall. Zillow and StreetEasy are paid by landlords and brokers, so the real prices and the real history stay locked behind them. `pricefixed` pulls it straight from the source instead.

- A tiny, dependency-free framework for pulling listings from **landlord-direct feeds**, the availability data landlords publish themselves to lease their own units.
- Every pull snapshots price and lease terms, so you keep **the history the listing sites throw away**.
- Output is a plain **SQLite** file. No account, no key, no lock-in. Point an AI agent at it and build whatever you want.

Scraping gets a bad name. But it is how the big real-estate companies got their data in the first place. They just block you when you try to get it back.

## Where this is going

Three steps, in order:

1. **The feeds.** Maintained, dependency-free scrapers for landlord-direct sources. NYC first, because it is the hardest and the most walled. This is what ships today.
2. **The inventory.** A published, open dataset of what those feeds return over time, so nobody has to run the scrapers to get the history.
3. **The algorithms.** Reverse-engineering how landlord pricing software actually sets your rent, in public, so the thing setting the price can finally be seen.

Contributors are welcome. This is going to be big and I am happy to go it alone, but you are welcome along.

## Quickstart

```bash
git clone https://github.com/pauljump/pricefixed
cd pricefixed
python3 scrape.py            # pull every source into ./listings.db
python3 scrape.py --list     # see available sources
python3 scrape.py --status   # counts in your db
```

No dependencies. Python 3.9+ standard library only.

```
$ python3 scrape.py --source stuytown
  331 listings (331 new, 0 updated) in 0.5s
$ python3 scrape.py --status
  nooklyn         1531 active
  avalonbay        250 active
  stuytown         331 active
  securecafe       253 active
  ...
  TOTAL           2632 active
```

## The data

One SQLite database, three tables:

| table | what |
|---|---|
| `listings` | current inventory: address, unit, beds/baths, price, sqft, lease terms, geo, raw source JSON |
| `price_history` | one snapshot per listing per pull, so you can recover every price and lease-term change over time |
| `pull_log` | when each source was pulled and how much moved |

Run it on a cron and `price_history` becomes something no listing site will sell you: the real trajectory of what every unit actually asked, over time.

## Point your agent at it

**The fastest start:** hand this repo to Claude or Codex and say *"read [`BUILD.md`](BUILD.md) and help me build an apartment database."* It asks you what you want — current inventory, price history, the full public record per building, or all of it — and then builds exactly that from the feeds and data here. That guided prompt is the front door.

You do not have to write the glue. The tools are the primitive; the inventory is yours to shape. Ask for *"every 1-bedroom under $3,000 that dropped its price this week"* and it composes the feeds, the history, and the building record to answer. See [`AGENTS.md`](AGENTS.md) for how any LLM should drive this repo.

The bigger move: point your agent at the source map ([`FEEDS.md`](FEEDS.md)) and the compile method ([`COMPILE.md`](COMPILE.md)), and it builds new adapters row by row. The ten below are reference implementations. Compiling the rest is a crank anyone, human or AI, can turn.

## Sources

Live landlord-direct feeds across NYC: big portfolios (AvalonBay, Beam Living's StuyTown, TF Cornerstone, Durst, Glenwood, Stonehenge, Ogden CAP), RentCafe/Yardi leasing portals (`securecafe`), AppFolio operators (`appfolio`), and the no-fee broker marketplace (`nooklyn`). Live counts are in the table below.

Plus the highest-leverage sources of all: **`corcoran`** and **`elliman`**, two brokerages. A big brokerage's public search returns not just its own exclusives but every listing syndicated to it through IDX/MLS — the REBNY RLS feed. So one brokerage adapter rides that syndication and reaches a large slice of the whole broker-listed market, no feed license required. Both pull **current, on-market listings only** — the same public availability a landlord posts about its own units, never the closed rent history the same APIs can serve. Compass is the same move next; see [`FEEDS.md`](FEEDS.md#brokerages--the-idxrls-backdoor) for how to add one.

This is the start, not the goal. The goal is every apartment in the city, then every city. Getting there means taking the walls down one at a time and keeping them down as they go back up. That fight is the project.

The full map of what is out there, tiered by how hard it is to pull and by what each source exposes, is in [`FEEDS.md`](FEEDS.md). Sites change constantly to stop exactly this, so the maintenance *is* the project. Every feed is health-checked; when one breaks it shows up as broken, not as silence.

<!-- FEED-STATUS:START -->
**Feed status** — 11/12 live, checked 2026-07-12

| source | status | listings | note |
|---|---|---|---|
| `appfolio` | 🟢 live | 23 |  |
| `avalonbay` | 🟢 live | 242 |  |
| `corcoran` | 🟢 live | 1365 |  |
| `durst` | 🟢 live | 25 |  |
| `elliman` | 🟢 live | 2340 |  |
| `glenwood` | 🟢 live | 26 |  |
| `nooklyn` | 🟢 live | 1522 |  |
| `ogdencap` | 🟢 live | 49 |  |
| `stonehenge` | 🟢 live | 78 |  |
| `stuytown` | 🟢 live | 316 |  |
| `tfcornerstone` | 🟢 live | 124 |  |
| `securecafe` | 🔴 down | — | returned 0 listings |
<!-- FEED-STATUS:END -->

## The public record

Live listings are only half of it. `pricefixed` also builds a standardized record of every NYC building and its public history, pulled fresh from [NYC Open Data](https://data.cityofnewyork.us). `build_record.py` assembles a `buildings` table (one row per lot, keyed by BBL: address, year built, units, class, owner) and a `building_events` timeline (permits, sales, violations, each with a date and a source). No rent data. All public record.

```bash
python3 build_record.py --list
python3 build_record.py --source pluto --limit 500   # sample a source
python3 build_record.py --boro BX --limit 20000      # one borough, every source, joined
python3 build_record.py                              # everything (large; it's all of nyc)
```

`--boro` (MN/BX/BK/QN/SI) is the one that makes the record *compose*: it scopes every source to a single borough, so ownership and violations and evictions all land on the **same buildings** instead of thin all-NYC samples that never overlap. Build one borough and the landlord portfolios below light up with real numbers.

Shipping now: **PLUTO** (the building spine), **DOB permits** (filing history), **HPD registrations** (ownership), **ACRIS sales** (recorded deeds), **HPD violations** and **complaints**, **DOB complaints**, **certificates of occupancy**, **evictions**, **housing litigation**, **311** (housing complaints), and **rent-stabilization** status (DHCR-derived unit counts from the taxbills.nyc scrape — a 2017 snapshot, tagged with its vintage so it's never mistaken for a live signal). A crosswalk (`pricefixed/engine/crosswalk.py`) joins a listing to its building's record by address, so an asking rent and its building's full public history sit together. Public data is building-level for most lots and unit-level for condo sales and currently-listed rentals.

Two engine passes turn the raw record into something you can act on:

- **Who owns what** (`python build_record.py --portfolios`) clusters buildings into landlord portfolios by shared HPD-registered business address, unmasking the single-purpose LLCs. Build one borough and it's concrete: in the Bronx, one registered business address ties together **96 buildings spread across 25 separate LLCs — 700 HPD violations, 77 evictions, and 250 complaints between them.** That's a real row from `--boro BX`, not a mock-up.
- **Dedupe** (`python scrape.py --dedupe`) collapses the same physical unit surfaced by more than one feed into one canonical listing, so a compiled inventory counts each apartment once.

## Prior art, and how this is different

NYC already has open-data heroes, and this is not trying to replace them. JustFix's [NYCDB](https://github.com/nycdb/nycdb) loads dozens of housing datasets into Postgres, and [Who Owns What](https://whoownswhat.justfix.org) maps landlord portfolios. Use them. They are excellent, and the public-record layer here stands on the same city datasets they do.

The difference is the join. `pricefixed` fuses that public record with **live listing feeds and their price history over time** in one standardized, per-building shape, dependency-free and built to be driven by an AI agent. The live asking-rent layer, snapshotted so the history is not thrown away, is the part nobody else maintains.

## Contributing

A new source is about 30 lines: subclass `SourceAdapter`, implement `pull()` to return listing dicts, register it. See any file in [`pricefixed/adapters/`](pricefixed/adapters/) and [`CONTRIBUTING.md`](CONTRIBUTING.md). PRs welcome.

## Get involved

No permission needed, no process to learn. Star it if you want it to exist. Open an [issue](../../issues) to report a broken feed or request a landlord. Send a PR to add a source. The fastest way to reach me is on X, [@paulljump](https://x.com/paulljump). Follow along and jump in when you feel like it.

## Please scrape responsibly

Targets are **landlord-direct availability feeds**: public data landlords publish to lease their apartments, not walled gardens behind a login. Keep it that way. Honor rate limits, the adapters are gentle by default, do not hammer, and do not touch anything that requires an account or defeats an access control. This is a transparency project, not a denial-of-service one.

## License

MIT. Take it, fork it, build a company on it. Just keep it open.
