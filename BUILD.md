# Build your own apartment database

Hand this repo to Claude or Codex and say: *"read BUILD.md and help me build an apartment database."* The agent asks you a few questions, then builds exactly what you want from the feeds and public data here.

This file is written for that agent. **If you are that agent: run the interview below, then execute only the methodology sections that match the answers. Be honest about the one thing this cannot do (see the boundary at the end).**

---

## What this repo gives you

- **Live listings** from 10 landlord-direct feeds (asking rent + lease terms), snapshotted every run so price history accrues over time. ~2,700 NYC units today, and the map to compile far more.
- **A public record of every NYC building** from NYC Open Data: sales (ACRIS), permits (DOB), ownership (HPD), and more.
- **A crosswalk** that joins any listing to its building's full public record by address → BBL.
- **A method** ([`COMPILE.md`](COMPILE.md)) to add any source in the map ([`FEEDS.md`](FEEDS.md)) — platforms first, one adapter for many landlords.

## The interview (agent: ask these, then act)

1. **Which city?** NYC is built out. Other cities: the platform adapters (RentCafe, AppFolio) port with a config change — see `FEEDS.md`.
2. **What do you actually want?** (any of these)
   - Current inventory + asking prices, right now
   - Price history over time — how asking rents move
   - A record of every building and its history — sales, permits, owners, violations
   - Specific public layers: 311, DOB permits, ACRIS sales, landlord/ownership, rent-stabilization, evictions
   - The join — each listing tied to its building's full public record
   - Everything — the full database
3. **How fresh?** A one-time snapshot, or kept up to date on a schedule?
4. **How much?** A neighborhood or a sample to start, or all of NYC?

## The methodology (agent: run the parts that match their answers)

### Seed current inventory + pricing
```bash
python3 scrape.py            # all live feeds -> listings.db
python3 scrape.py --list     # the sources
python3 scrape.py --source stuytown   # just one
```

### Keep it fresh — this is how price history is built
Put `python3 scrape.py` on a daily cron or GitHub Action. Every run snapshots price + lease terms into the `price_history` table, so the longer it runs, the deeper the history you own. Use `python3 healthcheck.py` to catch feeds that break (it writes a live status table and exits nonzero when one is down).

### Build the public building record
```bash
python3 build_record.py --source pluto             # the building spine (every lot)
python3 build_record.py --source acris_sales       # sale history: deeds, $ amount + date
python3 build_record.py --source dob_permits       # filing history
python3 build_record.py --source hpd_registrations # ownership
python3 build_record.py --limit 500 ...            # sample instead of all of NYC
```
Output is `record.db`: a `buildings` row per lot + a `building_events` timeline.

### Join listings to buildings (asking rent + full record per unit)
Use the crosswalk in `pricefixed/engine/crosswalk.py`: `bbl_for_address(address)` resolves a listing to its BBL, which keys the `buildings` / `building_events` tables. `python3 build_record.py --crosswalk` shows the join running on real listings.

### Add more sources (toward every apartment)
`FEEDS.md` is the full source map; `COMPILE.md` is how to turn any row into an adapter. `python3 new_adapter.py <name>` scaffolds one. Do platforms first — one adapter, many landlords.

## What you can and cannot get (agent: tell the user this plainly)

**Yes:**
- Current inventory + asking prices.
- Price history **from the day you start collecting** — it accrues forward as you run the feeds.
- Every building's **sale** history, permits, ownership, and violations — the public record, going back years.
- The join between a live listing and its building's full public history.

**No:**
- Rent price history from **before** you started collecting. Past *asking rents* are not public data, and no open source has them. (Past *sale* prices are public, via ACRIS — those you get. Past *rents*, you do not.) If you need backfilled rent history, that has to be sourced privately; this repo builds rent history forward from today.

## Big questions this answers

- "Every 1-bedroom under $3,000 that dropped its price this week." (feeds + `price_history`)
- "Who owns this building, and what's their violation record?" (record: `hpd_registrations` + violations)
- "What did units in this building last sell for?" (record: `acris_sales`)
- "Show me every unit a landlord has listed across the city, each with its building's history." (feeds + join + portfolios — portfolios on the roadmap)
- "Build me a rental-search site over all of it." (point your agent at `listings.db` + `record.db` and go)
