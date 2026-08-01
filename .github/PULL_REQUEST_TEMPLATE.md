## Contribution lane
- [ ] Listing source or adapter repair
- [ ] Public-record source
- [ ] Registry identity rule
- [ ] Data-quality fixture or audit
- [ ] Release, documentation, or tooling

## What this does
(one line and the public source or dataset identifier)

## If this adds or fixes a source
- [ ] It targets a **landlord-direct** availability feed (not a login-walled aggregator like StreetEasy/Zillow/RentHop)
- [ ] **Standard library only** — no new dependencies
- [ ] `python3 scrape.py --source <name>` returns a nonzero listing count
- [ ] The adapter keeps `raw_json`, and stores `lease_terms` as JSON when the source exposes per-term pricing
- [ ] Registered in `pricefixed/adapters/__init__.py`

## If this changes registry identity or coverage
- [ ] Preserves source provenance and does not overwrite source material
- [ ] States the identity status, matching method, and confidence effect
- [ ] Includes a positive fixture and a case the rule refuses to resolve
- [ ] Documents expected coverage and likely failure modes
- [ ] Does not convert an official dwelling count into an invented apartment identity

## Notes
(anything the reviewer should know — e.g. "endpoint needs a token scraped from the page first")
