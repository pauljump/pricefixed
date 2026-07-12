# How to compile every apartment

This is the point of the project: not nine scrapers, but a repeatable way to turn every source in [`FEEDS.md`](FEEDS.md) into a working adapter. This file is written to be handed to an AI agent (Claude, Codex) that then cranks through the map. A human can follow it just as well.

## The order of work

Do the highest-leverage sources first (this is why the map is tiered):

1. **Brokerages, for the IDX/RLS backdoor.** One brokerage adapter (Corcoran shipped; Elliman, Compass next) rides that brokerage's IDX/MLS syndication and pulls a large slice of the whole broker-listed market — no feed license. See the brokerage recipe below. Highest leverage per adapter.
2. **Platforms** (Tier 1). Each one is many landlords for one adapter. RentCafe, MRI ProspectConnect, AppFolio, Entrata, Funnel/Nestio. Crack the platform, then enumerate every NYC landlord on it and register each as a config entry, not a new file.
3. **Big portfolios** (Tier 2) that run their own sites.
4. **Broker marketplaces** (Tier 3).
5. **The walled aggregators** (Tier 4), last and hardest.

## Building one adapter (the loop)

For a landlord-direct or portfolio source:

1. **Find the source's own feed.** Open the landlord's "available apartments" page. In the browser network tab, find the request that returns the listings: usually a JSON API (`.../availability`, `/api/...`, `search/units`) or a static JSON blob the page loads. That URL is your target. If the page is server-rendered HTML with no API, the DOM is your target.
2. **Confirm it is landlord-direct and public.** It must be data the landlord publishes to lease their units. Never anything behind a login or an access control. If it needs an account, skip it.
3. **Verify the fields on a real sample.** Fetch one or two records and look at the actual keys. Do not trust field names from documentation; Socrata and vendor APIs rename things.
4. **Scaffold the adapter.** Run `python3 new_adapter.py <name>` to generate `pricefixed/adapters/<name>.py` prefilled from the template, then fill in `pull()`.
5. **Map to the schema.** Return a list of dicts using the fields in `pricefixed/core.py` (`LISTING_FIELDS`). Only `source_id` is required. Always keep `raw_json`. If the source exposes per-lease-term pricing, store it as JSON in `lease_terms` — that field is the most valuable thing in the database.
6. **Register it** in `pricefixed/adapters/__init__.py` (keep the map alphabetical).
7. **Prove it works.** `python3 scrape.py --source <name>` must print a nonzero count. Then `python3 healthcheck.py` to confirm it stays green.
8. **Ship it.** Open a PR (see `.github/PULL_REQUEST_TEMPLATE.md`).

## The platform recipe (the multiplier)

A platform adapter is worth ten landlord adapters. Once you have the platform's request shape working:

1. Write the `pull()` so it loops over a list of landlord/community configs (company code, portal slug, or subdomain).
2. Enumerate the NYC landlords on that platform (search the platform's directory, or find the code embedded in each landlord's own site) and add each as a config entry.
3. One file, one platform, dozens of landlords. Adding the next landlord is a one-line config change, not a new adapter.

Examples already in the repo: `securecafe.py` (Yardi/RentCafe portals), `durst.py` and `ogdencap.py` (MRI ProspectConnect). Copy their structure.

## The brokerage recipe (the IDX backdoor)

A brokerage adapter is the highest-leverage of all: it rides the brokerage's own IDX/MLS access to the REBNY RLS feed, so you pull far beyond that one brokerage's exclusives. The move:

1. **Find the brokerage's listing-search backend.** Open the brokerage's rental-search page, watch the network tab; it's usually a JSON API on an `*api*` subdomain (Corcoran: `backendapi.corcoranlabs.com/api/search/listings`, Elliman: `core.api.elliman.com`).
2. **Ask for active for-rent only.** POST the search with `transactionTypes:["for-rent"]` and **no** `sold`/`rented`/`closed`/`listingStatus` filter. Paginate.
3. **Confirm the syndication.** Look for `isIdx` / `isMLS` / `isVow` on the rows — those are listings from *other* brokers riding the feed. That is the multiplier.
4. **Add a defensive active-only filter** (see `corcoran.py`'s `_is_active`) so a closed/rented row can never leak into the open dataset even if the API's defaults change.
5. **Handle the key as public config.** Brokerage web APIs usually take the brokerage's own public web-app key (the one their site sends from every browser). Ship it as a default constant, overridable by env; when it rotates, the healthcheck goes red and you update it.

Example already in the repo: `corcoran.py`. Copy its structure for Elliman and Compass.

## Rules that keep this honest

- **Public, current listings only.** Landlord-direct feeds, platform availability, and brokerage *current on-market* listings are all fair game — they are what a landlord or broker publishes to lease a unit right now. Off-limits: anything behind a login or access control, the walled aggregators (Tier 4, a separate careful fight), and — for brokerages specifically — the *closed* sold/rented price history their backends can also serve. Stay on the currently-advertised side of that line.
- **Standard library only at runtime.** If a source needs a headless browser to *discover* its API, do that discovery yourself and ship an adapter that uses plain `fetch()` at runtime. The installed repo stays dependency-free.
- **Be gentle.** Honor rate limits. The framework already retries with backoff. Do not parallel-hammer one source.
- **Expect rot.** Sources change to stop exactly this. `healthcheck.py` surfaces breakage; fixing it is normal, ongoing work. The maintenance is the project.

## Working in parallel

Rows in `FEEDS.md` are independent. Hand different tiers or platforms to different agents at once. Each produces one file (or one platform file with many configs), each verifies with `scrape.py --source <name>`, each opens its own PR. That is how nine becomes everything.
