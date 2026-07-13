# HANDOFF — the self-maintaining toolkit build

**Status: foundation landed, 6 enrichers + 3 spine pieces remain.** This doc is written
so any agent (Codex or Claude) can pick up exactly where we stopped. Read it top to
bottom, then `AGENTS.md`, `COMPILE.md`, and `pricefixed/enrichment/core.py`.

Session stopped mid-fan-out because the account hit its usage limit, not because of any
blocker. Everything below is decided and scoped; it's execution from here.

---

## The mission (why this build exists)

pricefixed is turning from "a pile of scrapers" into **the gold-standard toolkit an AI
agent can one-shot a whole NYC inventory from, and that keeps itself provably fresh.**
An open data project normally earns trust from a brand. pricefixed has none by design
("no company, just open source"). So trust comes from something else: **visible,
continuous, agent-run maintenance.** You trust it because you can watch it keep itself
alive and verified, in the open, on a heartbeat. Maintenance is the product.

The database itself is a LATER phase. This phase perfects the TOOLS that build and
maintain it.

### Locked decisions (do not relitigate)

- **Coverage number: meter internal, counts external.** The coverage % (built vs the
  mapped universe) is the INTERNAL finish-line meter an agent drives toward zero. The
  PUBLIC surface (README) shows raw live counts + freshness only ("6,401 live, verified
  2h ago"), never a % against "every apartment" — a public denominator invites a fight
  and undercuts the honesty that IS the trust model.
- **Enrichment: do them all, public sources only.** Build all seven; state openly we add
  more on request. Enrichment stays strictly on public civic data (same category as the
  building record). The rent history + pricing model stay PRIVATE, elsewhere. Never let a
  closed-rent or private-index source into this repo.
- **Promise the method, not completeness.** The confidence write-up promises "point an
  agent here and it builds the inventory, here's roughly how long," never "we have every
  apartment." Confidence lives in the machine and the map.
- **Alert channel: GitHub issues.** The monitor opens/updates a GitHub issue on drift;
  GitHub emails Paul. Keeps the heartbeat visible in the repo.
- **Nothing autonomous spends.** The only automated piece is the free HTTP monitor. It
  never fires an LLM. When something breaks, Paul (with CLI Claude/Codex) triggers the
  fix. The monitor's job is to alert with a ready-to-run fix recipe, not to self-heal.
- **Stdlib only.** No third-party deps, ever. This shaped enrichment: geometry is
  hand-rolled (`haversine`, `point_in_polygon` in `enrichment/core.py`).
- **Commit hygiene: stage files EXPLICITLY, never `git add -A`.** Concurrent sessions
  work this repo.

---

## DONE (committed locally, commit `enrichment: layer foundation + transit...`, NOT pushed)

- **Spine geo columns.** `pricefixed/record/core.py` — `BUILDING_COLUMNS` gained
  `latitude, longitude, community_district, census_tract`; the `init_record_db` ALTER
  loop adds them to fresh + existing dbs. `pricefixed/record/pluto.py` now selects and
  stores them (`latitude, longitude, cd, ct2010`).
- **Enrichment layer base** — `pricefixed/enrichment/core.py`. Read this first; it's the
  contract. Provides: `EnrichmentSource` (subclass, set `name`/`description`/`join_key`/
  `columns`, implement `enrich(conn, limit, boro)`), the `building_enrichment` table
  (bbl PK, extensible columns via `ensure_columns`), `upsert_enrichment`,
  `buildings_with_points` / `buildings_with_areas` iterators, `haversine`,
  `point_in_polygon(lat, lng, ring)` (ring = list of `(lng, lat)` GeoJSON order),
  `census_geoid(boro, tract)`.
- **Self-registering registry** — `pricefixed/enrichment/__init__.py`. Drop an
  `EnrichmentSource` file in the folder and it auto-registers into `ENRICHERS`. A broken
  or drifted adapter is skipped with a warning, never fatal. No central list to edit.
- **Transit enricher (1 of 7), verified** — `pricefixed/enrichment/transit.py`. Nearest
  subway + walk distance from MTA dataset `39hk-dx4f` (496 stations). Self-verify:
  396/400 Manhattan buildings enriched, max distance 2992m (Battery tip), sane. Use it
  as the TEMPLATE for the point-join enrichers.

Everything is additive: the 12 feeds, the record layer, and the CI healthcheck are
untouched and still pass. `python3 -c "import pricefixed"` and the enrichment registry
import clean.

---

## TODO — the six remaining enrichers

Each is ONE new file `pricefixed/enrichment/<name>.py` with an `EnrichmentSource`
subclass. It auto-registers — do NOT edit `__init__.py`. Match `core.py`'s comment style
(teach the WHY/mechanism). **VERIFY dataset ids and field names LIVE** (curl / a quick
fetch) before coding — do not trust the hints below blindly. **Self-verify bar: an
adapter is not done until it runs on the sample and attaches sane values to >0 buildings
(no all-null, no all-same-value bugs).** The harness pattern (swap the name/boro):

```python
import pricefixed.record.core as rc
from pricefixed.record.pluto import PlutoSource
conn = rc.init_record_db('/tmp/enr_X.db')
PlutoSource().run(conn, limit=400, boro=1)          # pick a borough where the signal is dense
from pricefixed.enrichment.X import XSource
XSource().run(conn, boro=1)
# then SELECT from building_enrichment and eyeball the values
```

| name | class | join_key | source (VERIFY live) | columns | sample |
|---|---|---|---|---|---|
| **energy** | `EnergySource` | `bbl` | NYC LL84/LL97 Energy & Water Disclosure (keyed by BBL — the clean bbl-join reference). Field names are very long; BBL comes plain `4006520042` AND hyphenated `1-01206-0001`, normalize both to 10-digit. | `energy_star_score`, `site_eui`, `ghg_intensity` | boro=1, limit 2000 (disclosure only covers >25k sqft, low match rate is expected) |
| **demographics** | `DemographicsSource` | `area` | Census ACS 5-year `api.census.gov/data/{year}/acs/acs5` (keyless at low volume; the earlier run saw a 302 redirect — follow it / use the resolved host). Vars: `B19013_001E` (median hh income), `B25064_001E` (median gross rent), `B25003_003E`/`B25003_001E` (renter/total occ). Query per county: state=36, counties MN=061 BX=005 BK=047 QN=081 SI=085, `&for=tract:*&in=state:36+county:XXX`. Join via `census_geoid(bbl_first_digit, census_tract)`. Treat sentinel negatives (-666666666) as null. | `median_household_income`, `median_gross_rent`, `pct_renter_occupied` | boro=3, limit 600 |
| **flood** | `FloodSource` | `point` (PIP) | FEMA NFHL / NYC flood-zone polygon dataset (Socrata returns geometry as GeoJSON in `the_geom`). Parse rings, `point_in_polygon` each building; MultiPolygon = OR over rings; bbox-prefilter per polygon for speed. Watch coordinate order (lng,lat). | `flood_zone` (e.g. "AE"), `in_floodplain` (0/1) | boro=4 (Queens, waterfront); PASS = most tagged AND a nonzero subset in-floodplain (all-0 or all-1 = bug) |
| **schools** | `SchoolsSource` | `point` (PIP) | NYC DOE school-zone polygon datasets (ES zone, with district/DBN label + GeoJSON geometry). PIP each building. OK to fill just one column if only one dataset is clean. | `school_district` (int), `elem_school_zone` | boro=3 (Brooklyn districts ~13–23,32) |
| **safety** | `SafetySource` | `area` | NYPD complaint data aggregated per precinct via Socrata server-side `$select=addr_pct_cd,count(1)&$group=addr_pct_cd` (one small query, NOT millions of rows). Map building→precinct via NYC "Police Precincts" polygon dataset + `point_in_polygon`. | `police_precinct` (int), `precinct_complaints_ytd` (int) | boro=1 (Manhattan precincts 1–34) |
| **amenities** | `AmenitiesSource` | `point` | OpenStreetMap Overpass API (`overpass-api.de/api/interpreter`). CRITICAL: do NOT query per building. One bbox query for all `shop=supermarket/grocery`, `leisure=park`, `amenity=restaurant` (`out center;` for ways), then count within radius locally via `haversine`. Backoff/mirror on rate-limit. | `grocery_within_500m`, `parks_within_800m`, `restaurants_within_400m` | boro=1, limit 150 (small, Overpass-friendly) |

If an adapter genuinely can't self-verify in stdlib at a workable size (flood/schools/
safety are the hard tier), do NOT ship broken code — write the best version, mark its
ledger status `recon`, and put the precise blocker + what a production build needs in its
`fix_recipe`. That honesty IS the design.

Also add a CLI `enrich.py` at repo root, mirroring `build_record.py` (`--source`,
`--list`, `--status`, `--boro`, `--limit`, `--db record.db`), iterating `ENRICHERS`.

---

## TODO — the three spine pieces (the actual "gold standard" payload)

### 1. The ledger — `sources.json` + `pricefixed/ledger.py`

The single source of truth. One machine-readable file, everything renders from it.

`sources.json`: array of rows, one per source across ALL kinds:
```json
{ "id": "transit", "kind": "enrichment", "tier": "enrichment",
  "title": "Nearest subway", "mechanism": "MTA 39hk-dx4f + haversine",
  "difficulty": "easy", "join_key": "point", "est_units": null,
  "status": "shipped", "fix_recipe": "re-verify dataset 39hk-dx4f field names; ...",
  "terms": false }
```
Seed it from FEEDS.md (feeds + record + the mapped/unbuilt rows) + the 7 enrichers.
`kind` ∈ feed|record|enrichment. `status` ∈ shipped|mapped|recon.

`ledger.py` responsibilities:
- **Reconcile** `sources.json` against the live registries (`ADAPTERS`,
  `RECORD_SOURCES`, `ENRICHERS`) — flag drift (in code but not ledger, or vice versa).
- **Live counts + freshness**: feeds from `listings.db` (pull_log), record from
  `record.db` (record_source_log), enrichment from `building_enrichment` /
  `enrichment_source_log`. Freshness = last pulled_at per source.
- **`coverage` command (INTERNAL view)**: built vs mapped universe, and the unbuilt rows
  ranked by units-per-effort. This is the finish-line meter. Percentage lives HERE only.
- **`render` (PUBLIC view)**: rewrite a README table of live counts + freshness. NO
  percentage. This is the trust surface.
- **Self-verify bar** (`verify.py` or a ledger method): per-kind proof run on a small
  sample — feed: rows>0 & all active & no closed-status leak; record: rows>0;
  enrichment: enriched>0 & values in range. A source isn't "shipped" until proof passes.

### 2. The one-shot build spec — `BUILD_EVERYTHING.md`

Agent-agnostic (Claude or Codex). Reads `sources.json`; for every unbuilt row, build per
`COMPILE.md` + the relevant base contract, self-verify, flip its ledger status, update
counts; report coverage when it stops. Opens with an HONEST time estimate for a cold full
build (Tier 4 needs headless recon, so a full run is ~a day). This file is the
embodiment of "point your agent here and it builds the inventory."

### 3. The monitor → GitHub issue loop

- `monitor.py`: run the self-verify/healthcheck across all kinds; on any red, emit a
  GitHub issue body that INCLUDES the `fix_recipe` from the ledger for each down source.
- `.github/workflows/monitor.yml`: on the existing daily cron, run monitor; open or
  update a single "feed status" issue when something's red (via `gh` / the issues API),
  so GitHub emails Paul. Extends the existing `healthcheck.yml` pattern (which already
  commits the README refresh). The FIX stays human-triggered — nothing autonomous.

### Soft pieces
- **Star-ask**: one line in `AGENTS.md` and `llms.txt`, phrased as an instruction the
  agent surfaces to its human when the tool delivers value ("if this saved you a scraper
  stack, star it so the map keeps getting maintained"). Not a banner.
- **Confidence write-up**: a short "what this does / how long a full run takes" section,
  method-promise voice.

---

## Suggested build order

1. Finish the 6 enrichers (parallelizable; transit is the template) + `enrich.py`.
2. `sources.json` + `ledger.py` (coverage internal / render public) + the self-verify bar.
3. `monitor.py` + `monitor.yml`.
4. `BUILD_EVERYTHING.md` + star-ask + confidence write-up.
5. Adversarial-verify the whole thing, then push.

Do the whole thing as the factory build shape: contract → parallel builds → prove →
adversarial-verify before landing. Stage every file explicitly.
