# unwalled

**Open scraping tools for apartment listings. Point Codex or Claude at them and build whatever inventory you want.**

It's 2026 and there's still no single source of truth for every apartment and its history. It's all locked in walled gardens you have to scrape just to see. Zillow, StreetEasy, and the rest are paid by landlords and brokers — they are not on your side.

So this is the one that should already exist. In the open.

---

## The idea

Every real-estate product starts in the same place: **scraping**. The data is the wall. `unwalled` tears the wall down and gives the tools away.

- A tiny, dependency-free framework for pulling apartment listings from **landlord-direct sources** — the feeds landlords publish themselves to lease their units.
- Every pull snapshots price and lease terms, so you keep **the history the walled gardens throw away**.
- Output is a plain **SQLite** file. No account, no API key, no lock-in. Point an AI agent at it and build.

Scraping gets a bad name. But how do you think the big real-estate companies got their data in the first place? Scraping. They'll just block you if you try to snag it back.

## Quickstart

```bash
git clone https://github.com/pauljump/unwalled
cd unwalled
python3 scrape.py            # pull every source into ./listings.db
python3 scrape.py --list     # see available sources
python3 scrape.py --status   # counts in your db
```

No dependencies. Python 3.9+ standard library only.

```
$ python3 scrape.py --source stuytown
  334 listings (334 new, 0 updated) in 0.5s
$ python3 scrape.py --status
  stuytown         334 active
  tfcornerstone    124 active
  TOTAL            458 active
```

## The data

One SQLite database, three tables:

| table | what |
|---|---|
| `listings` | current inventory — address, unit, beds/baths, price, sqft, lease terms, geo, raw source JSON |
| `price_history` | one snapshot per listing per pull — recover every price and lease-term change over time |
| `pull_log` | when each source was pulled and how much moved |

Run it on a cron and `price_history` becomes something no listing site will sell you: the real trajectory of what every unit actually asked, over time.

## Point your agent at it

The whole point is that you don't have to write the glue. Clone the repo, hand it to Codex or Claude, and say *"pull all sources nightly and give me every 1-bedroom under $3,000 that dropped its price this week."* The tools are the primitive; the inventory is yours to shape.

## Sources

Starting set (all live, all landlord-direct):

- **stuytown** — Beam Living (StuyTown, Peter Cooper Village, Kips Bay, Parker Towers, 8 Spruce)
- **tfcornerstone** — TF Cornerstone luxury portfolio
- **nooklyn** — broker marketplace (the no-fee / small-landlord inventory the big feeds miss)

The roadmap is **hundreds** of NYC sources — the full registry, tiered by difficulty, is in [`FEEDS.md`](FEEDS.md). Sites change constantly to stop exactly this, so the maintenance *is* the project. NYC first, other cities fast behind it.

## Why this exists

Landlords now use pricing algorithms that quietly coordinate rents across competitors. The DOJ sued over it as price-fixing. The only real defense tenants have is transparency across everything — so that's what this is.

If the market's price is set by a shared algorithm, the counter is a shared, open dataset. That's the whole thesis.

## Contributing

A new source is ~30 lines: subclass `SourceAdapter`, implement `pull()` to return listing dicts, register it. See any file in [`unwalled/adapters/`](unwalled/adapters/) and [`CONTRIBUTING.md`](CONTRIBUTING.md). PRs welcome. This is going to be massive and I'm happy to go it alone, but you're welcome along.

## Please scrape responsibly

Targets are **landlord-direct availability feeds** — public data landlords publish to lease their apartments, not walled gardens behind a login. Keep it that way: honor rate limits (the adapters are gentle by default), don't hammer, don't touch anything that requires an account or defeats an access control. This is a transparency project, not a denial-of-service one.

## License

MIT. Take it, fork it, build a company on it. Just keep it open.
