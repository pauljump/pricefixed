# Coverage-growth pass, 2026-07-30/31

Run order, each step depends on the last:

1. `extract_all.py` — raw, un-deduped `(source, address, unit, zip, source_ref)` pull
   from the four archives (StreetEasy/Elliman/Corcoran/Vayo `all_nyc_units`) straight to
   `extracted_addresses.csv`. No BBL resolution, no catalog writes. Elliman's `address`
   field embeds the unit in the string when its `unit` column is blank — this reuses the
   live adapter's own `_address_and_unit()` parser, don't re-roll that logic.
2. `build_hierarchy.py` — resolves each row to a BBL using the catalog's own exact-match
   rule (address + zip, mirroring `_resolve_bbl`), with one extra tiebreak: if the raw
   unit label matches exactly one candidate's official condo `unit_designation`, that
   wins. Writes `hierarchy.db` (`units` / `ambiguous` / `unresolved`), never touches
   `catalog.db`.
3. `merge_known.py` — merges `hierarchy.db`'s resolved rows into `catalog.db`, tagged
   with their real source. Classifies every `vayo_all_nyc_units` row by `source_systems`
   first and drops `PLUTO_INFERRED` rows — those are synthetic placeholder unit numbers
   (PLUTO's building-level count turned into fake "unit 1..N" labels), not observed
   evidence. This check is load-bearing; skipping it silently halves the real yield with
   fake units that look identical to real ones downstream.
4. `merge_single_family.py` — one unit per BBL where PLUTO `units_res=1` and nothing was
   ever named there. The building IS the dwelling; no label is invented.
5. `merge_tradable_tiebreak.py` — for the still-ambiguous rows from step 2, if exactly
   one candidate BBL is residential (PLUTO `units_res>0`) and the rest aren't (garage/
   parking/commercial annex sharing the civic address), the residential one wins. Same
   PLUTO_INFERRED classification as step 3.
6. `merge_condo_unit_lots.py` — direct pass over `official_unit_lots` (DOF's condo unit
   registry, imported earlier): every `unit_lot_bbl` with a real `unit_designation` and
   zero named units gets one. This is DOF's own tax registration of the individual unit,
   the strongest evidence tier used all session, not an inference.

**Result: 514,306 -> 2,750,889 canonical units** (12.4% -> 74.3% of the 3,705,000
citywide target).

## Run it reproducibly

The July 2026 run used local archive copies, but the scripts no longer encode those
machine paths. A contributor needs a catalog database with the prerequisite PLUTO,
PAD, and official condo-unit-lot imports, plus four archive SQLite inputs. All inputs
are explicit:

```bash
python3 tools/merges/run.py \
  --catalog-db /data/catalog.db \
  --work-dir /data/pricefixed-merge-work \
  --streeteasy-db /archives/se_listings.db \
  --elliman-db /archives/elliman_mls.db \
  --corcoran-db /archives/corcoran.db \
  --vayo-db /archives/all_nyc_units.db
```

The runner creates `extracted_addresses.csv` and `hierarchy.db` in `--work-dir`, then
runs all six steps in order. The input catalog is updated in place, so use a copy for
experimentation. Each direct merge is idempotent at the catalog-row level, but the
runner deliberately rebuilds its intermediate CSV and hierarchy database on every run.

The archive inputs are not distributed in this repository. Before publishing a build,
confirm that every source can legally be redistributed or document it as a
reproducibility dependency in the release manifest.

## What didn't work, and why it matters

- **Bulk DOB CofO data has no unit labels**, only `number_of_dwelling_units` — same
  granularity as PLUTO. Confirmed live against both `bs8b-p36w` and `pkdm-hqz6`
  before building anything. If revisiting the ~739 remaining 21+-unit buildings with
  zero named units, it needs individual scanned-document retrieval, not a bulk pull.
- **PAD address-count == PLUTO units_res is not a safe tiebreak for 2-family lots.**
  Tested against 62,347 candidates: only 4,585 (7.4%) were genuinely two dwellings on
  the same street ("28 JANE ST" / "30 JANE ST"). The other 57,762 were corner lots with
  two frontages on the *same* building ("127 PEARL ST" = "80 BEAVER ST"). Running this
  at full scale would have silently created ~115,000 fake units. Only the same-street
  subset is safe.
- **The dominant remaining gap is 2-family homes**: 130,504 lots with one civic address
  covering two legally separate dwellings (~261,000 units). NYC's Multiple Dwelling Law
  largely exempts owner-occupied 1-2 family buildings from HPD registration, so they
  structurally never generate the violation/complaint trail every other source here
  rode on. The only plausible public lever is the NYS voter file (apartment-level,
  ~5M NYC registrations) — but unlike everything else pulled this session, that
  requires a formal request to NYS BOE under NY election law, not an open API pull.

## Still on the table, not yet run

- **ACRIS staging backlog**: the archived `acris-unit-source.db` has 548,038 rows
  already downloaded, only 50,000 resolved. 136,538 rows (`resolved_at IS NULL`) are
  available for a resumable rerun. Use the bounded runner first:

  ```bash
  python3 tools/merges/run_acris_backlog.py \
    --catalog-db /data/catalog.db \
    --stage-db /archives/acris-unit-source.db \
    --batch-size 1000 --max-batches 1 --dry-run
  ```

  Remove `--dry-run` to process one batch. Use `--max-batches 0` to continue until
  the queue is empty; the runner stops below its free-space threshold and appends
  JSON progress records when `--log` is supplied.
- Same-street 2-family duplexes (4,585 buildings / 9,170 units) — the safe subset of
  the PAD-count tiebreak above, never merged.
- NYS voter file — blocked on Paul filing the request.

## Build artifacts

`extracted_addresses.csv` and `hierarchy.db` are reproducible intermediates, not
release artifacts. Keep them in the chosen work directory or regenerate them with the
runner. Publish only the versioned, payload-free data bundle described in
[`DATA.md`](../../DATA.md), with the source commit and input provenance in its manifest.
