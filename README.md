# pricefixed

[![feed status](https://github.com/pauljump/pricefixed/actions/workflows/healthcheck.yml/badge.svg)](https://github.com/pauljump/pricefixed/actions/workflows/healthcheck.yml) · **launch page: [pricefixed.polyfeeds.dev](https://pricefixed.polyfeeds.dev)**

**Open tools for pulling NYC apartment listings, public records, and unit history into one place.**

Pricefixed is software first. The repo lets you pull public listing data, keep the
price history the listing sites throw away, and build a local apartment database with
the source attached to every record.

I have a citywide build locally, but the multi-gigabyte database is **not on GitHub
yet**. [`DATA.md`](DATA.md) explains what will be in the first public download and how
to export CSVs from a local build.

The rent number on your lease was not set by a person. It was set by software.
Landlords feed their vacancies into shared pricing tools like RealPage's YieldStar,
and those tools can push rents up across competitors. The Department of Justice sued
over it and called it what it is: price-fixing.

You cannot figure out what the software is doing without the data it feeds on. Almost
none of that data is public in a useful shape. So that is where this starts: pull the
housing data into the open, owned by no one, so anyone can build on it.

To be clear: this is the data layer. The part that proves how rent gets set comes
later.

`pricefixed` starts with the hard part every real-estate project starts with: getting the data. It gives those tools away.

If this should exist in public, please star the repo. Stars help this reach the people
who can check the work, add sources, and build useful things on top of it.

---

## What ships today

| piece | status | how to use it |
|---|---|---|
| Listing collectors | maintained | Run `python3 scrape.py` to create your own `listings.db` and preserve future price history. |
| Building public record | maintained | Run `python3 build_record.py` against NYC public sources. |
| Housing registry builder | maintained | Run `catalog.py` to turn listings and public records into building/unit records. |
| Citywide build | built, not yet published | The July 31, 2026 local build contains 2,750,889 unit records. It still needs a public download before anyone else can use it directly. |

That 2.75M number is not a claim that we found every NYC home. NYC has about 3.7M
housing units, so this is close to 75% by the count we are using. Every row keeps the
source that got it there, and the known gaps are written down in [`CATALOG.md`](CATALOG.md).

## The idea

The data is the wall. Zillow and StreetEasy are paid by landlords and brokers, so the
real prices and the real history stay locked behind them. `pricefixed` pulls from the
source instead.

- A tiny, dependency-free framework for pulling listings from **landlord-direct feeds**, the availability data landlords publish themselves to lease their own units.
- Every pull snapshots price and lease terms, so you keep **the history the listing sites throw away**.
- Output is a plain **SQLite** file. No account, no key, no lock-in. Point an AI agent at it and build whatever you want.

Scraping gets a bad name. But it is how the big real-estate companies got their data in the first place. They just block you when you try to get it back.

## Where this is going

The order is simple:

1. **Pull the feeds.** Keep public listing data before it disappears.
2. **Publish the inventory.** Make the housing layer public enough for other people to use.
3. **Show how rent gets set.** Use the same kind of data the pricing tools use, and make the pattern visible.

Contributors are welcome. This is big enough that it should not be one person's thing.

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

## Your local data

One SQLite database, three tables:

| table | what |
|---|---|
| `listings` | current inventory: address, unit, beds/baths, price, sqft, lease terms, geo, raw source JSON |
| `price_history` | one snapshot per listing per pull, so you can recover every price and lease-term change over time |
| `pull_log` | when each source was pulled and how much moved |

Run it on a cron and `price_history` becomes something no listing site will sell you: the real trajectory of what every unit actually asked, over time.

## Public download

The repo does **not** currently include the citywide database. There is no GitHub
download for the 2.75M-unit build yet.

When the first snapshot is published, it will be a normal release download with:

- `units.csv`
- `unit_observations.csv`
- `sources.csv`
- `manifest.json`
- `quality-report.json`

No raw source dumps. No private working files. Just the rows people need to inspect,
join, challenge, and build on.

[`DATA.md`](DATA.md) has the file layout and export command. [`REGISTRY.md`](REGISTRY.md)
explains what counts as a real unit, what stays as a gap, and how to contribute without
asking anyone to trust a mystery row.

## Point your agent at it

**The fastest start:** hand this repo to Claude or Codex and say *"read [`BUILD.md`](BUILD.md) and help me build an apartment database."* It asks you what you want — current inventory, price history, the full public record per building, or all of it — and then builds exactly that from the feeds and data here. That guided prompt is the front door.

You do not have to write the glue. The tools are the primitive; the inventory is yours to shape. Ask for *"every 1-bedroom under $3,000 that dropped its price this week"* and it composes the feeds, the history, and the building record to answer. See [`AGENTS.md`](AGENTS.md) for how any LLM should drive this repo.

The bigger move: point your agent at the source map ([`FEEDS.md`](FEEDS.md)) and the compile method ([`COMPILE.md`](COMPILE.md)), and it builds new adapters row by row. The ten below are reference implementations. Compiling the rest is a crank anyone, human or AI, can turn.

## Sources

Live landlord-direct feeds across NYC: big portfolios, RentCafe/Yardi portals,
AppFolio operators, MRI-backed sites, broker search sources, and the no-fee broker
marketplace Nooklyn. Live counts are in the table below.

Brokerage sources like **`corcoran`** and **`elliman`** stay named because people need
to know where a row came from. These adapters only pull current public listings, not
closed rent history. See [`FEEDS.md`](FEEDS.md#brokerages-and-idxrls-syndication) for
how that works.

This is the start, not the goal. The goal is every apartment in the city, then every
city. Getting there means knocking down one wall at a time and keeping track when the
walls move.

The full source map is in [`FEEDS.md`](FEEDS.md). Sites change constantly, so the
maintenance is part of the work. Every feed is health-checked; when one breaks it
shows up as broken, not as silence.

<!-- FEED-STATUS:START -->
**Feed status** — 11/12 live, checked 2026-08-27

| source | status | listings | note |
|---|---|---|---|
| `appfolio` | 🟢 live | 17 |  |
| `avalonbay` | 🟢 live | 220 |  |
| `corcoran` | 🟢 live | 1363 |  |
| `durst` | 🟢 live | 20 |  |
| `elliman` | 🟢 live | 2275 |  |
| `glenwood` | 🟢 live | 36 |  |
| `nooklyn` | 🟢 live | 1260 |  |
| `ogdencap` | 🟢 live | 55 |  |
| `stonehenge` | 🟢 live | 65 |  |
| `stuytown` | 🟢 live | 255 |  |
| `tfcornerstone` | 🟢 live | 105 |  |
| `securecafe` | 🔴 down | — | returned 0 listings |
<!-- FEED-STATUS:END -->

## The public record

Live listings are only half of it. `pricefixed` also builds a public record for NYC
buildings from [NYC Open Data](https://data.cityofnewyork.us). `build_record.py`
creates a `buildings` table and a `building_events` table: permits, sales,
violations, complaints, evictions, and more. No private rent data. Public records only.

```bash
python3 build_record.py --list
python3 build_record.py --source pluto --limit 500   # sample a source
python3 build_record.py --boro BX --limit 20000      # one borough, every source, joined
python3 build_record.py                              # everything (large; it's all of nyc)
```

`--boro` (MN/BX/BK/QN/SI) is the useful one. It pulls every source for one borough, so
owners, violations, evictions, complaints, and permits all land on the same buildings
instead of random citywide samples that never line up.

Shipping now: **PLUTO** buildings, **DOB** permits, **HPD** registrations, violations
and complaints, **ACRIS** sales, certificates of occupancy, evictions, housing court,
311 housing complaints, and rent-stabilized unit counts from taxbills.nyc. A crosswalk
joins a listing to its building, so an asking rent and the building's public history
can sit together.

## The registry

`catalog.py` is how the repo turns messy source files into a clean building/unit
registry. It keeps the original source, then records how the project matched that row
to a building and unit.

A unit only gets counted when the source gives a real unit label and the address maps
cleanly to an official NYC building ID. If the match is messy, it stays unresolved
instead of getting guessed into the data. See [`CATALOG.md`](CATALOG.md) for the full
rules.

The current citywide build reached **2,750,889 unit records** on July 31, 2026. That is
a useful milestone, not a guarantee that every NYC home has been found. The biggest
gap is buildings where public records say how many homes exist but do not name the
units. The build steps and limits are documented in
[`CATALOG.md`](CATALOG.md) and [`tools/merges/README.md`](tools/merges/README.md).

```bash
python3 catalog.py --record record.db --listings listings.db --db catalog.db
python3 catalog.py --db catalog.db --status
python3 catalog.py --source hpd_violations --boro BX --limit 1000 --db catalog.db
python3 catalog.py --source hpd_omo_work_orders --boro BX --limit 1000 --db catalog.db
python3 catalog.py --source acris_property_legals --boro MN --limit 1000 --db catalog.db
python3 acquire.py --db catalog.db --source acris_unit_legals --page-size 10000 --pages 1
python3 catalog.py --source vayo_all_nyc_units --vayo-db /path/to/all_nyc_units.db --limit 25000 --db catalog.db
python3 catalog.py --source vayo_streeteasy_unit_summary --vayo-db /path/to/se_listings.db --limit 10000 --db catalog.db
python3 catalog.py --source vayo_elliman_mls_archive --vayo-db /path/to/elliman_mls.db --limit 25000 --db catalog.db
python3 catalog.py --source vayo_corcoran_archive --vayo-db /path/to/corcoran.db --limit 10000 --db catalog.db
python3 catalog.py --source annualized_sales --boro MN --limit 1000 --db catalog.db
python3 catalog.py --source evictions --boro BX --limit 1000 --db catalog.db
python3 catalog.py --source dob_now_jobs --boro MN --limit 1000 --db catalog.db
python3 catalog.py --source hpd_registration_coverage --boro BX --db catalog.db
python3 catalog.py --source condo_units --limit 1000 --db catalog.db
python3 catalog.py --source pad_addresses --zips 10001,10002 --limit 10000 --db catalog.db
python3 catalog.py --source pad_listing_zips --listings listings.db --db catalog.db
python3 catalog.py --source listings --listings listings.db --db catalog.db
python3 catalog.py --source derive_addressable_units --limit 10000 --derive-batches 1 --db catalog.db
python3 catalog.py --coverage --listings listings.db --db catalog.db
```

Two engine passes turn the raw record into something you can act on:

- **Who owns what** (`python build_record.py --portfolios`) groups buildings by shared
  HPD business address, so one landlord hiding behind a pile of LLCs can still show up
  as one pattern. In the Bronx, one business address ties together **96 buildings
  across 25 LLCs, with 700 HPD violations, 77 evictions, and 250 complaints.** Real
  row, not a demo.
- **Dedupe** (`python scrape.py --dedupe`) finds the same apartment when it shows up in
  more than one feed, so you do not count it twice.

## Prior art, and how this is different

NYC already has good open-data projects. JustFix's [NYCDB](https://github.com/nycdb/nycdb)
loads a ton of housing datasets into Postgres, and [Who Owns What](https://whoownswhat.justfix.org)
maps landlord portfolios. Use them. They are great.

The difference is the join. `pricefixed` puts public building records next to live
listing feeds and their price history. The live asking-rent history is the part nobody
keeps in public.

## Contributing

A new source can be small: subclass `SourceAdapter`, implement `pull()`, register it.
See any file in [`pricefixed/adapters/`](pricefixed/adapters/) and
[`CONTRIBUTING.md`](CONTRIBUTING.md). PRs welcome.

## Get involved

No permission needed. Star it if you want it to exist. Open an [issue](../../issues)
to report a broken feed or request a source. Send a PR to add one. The fastest way to
reach me is on X, [@paulljump](https://x.com/paulljump).

## Please scrape responsibly

Targets are **public availability feeds**: data posted so apartments can be rented,
not anything behind a login. Keep it that way. Be gentle. Do not hammer sites. Do not
touch anything that requires an account or breaks access controls. This is a
transparency project, not a spam tool.

## License

MIT. Take it, fork it, build a company on it. Just keep it open.
