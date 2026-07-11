## What this does
(one line — e.g. "adds an adapter for Glenwood Management")

## If this adds or fixes a source
- [ ] It targets a **landlord-direct** availability feed (not a login-walled aggregator like StreetEasy/Zillow/RentHop)
- [ ] **Standard library only** — no new dependencies
- [ ] `python3 scrape.py --source <name>` returns a nonzero listing count
- [ ] The adapter keeps `raw_json`, and stores `lease_terms` as JSON when the source exposes per-term pricing
- [ ] Registered in `pricefixed/adapters/__init__.py`

## Notes
(anything the reviewer should know — e.g. "endpoint needs a token scraped from the page first")
