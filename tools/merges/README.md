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

- **Targeted DOB occupancy documents**: the DOB NOW public portal exposes property
  profiles, Certificates of Occupancy, and Schedules of Occupancy; BIS covers older
  records. Export the highest-value queue from the current catalog before retrieving
  documents one property at a time:

  ```bash
  python3 tools/merges/export_gap_targets.py \
    --catalog-db /data/catalog.db \
    --out /data/dob-occupancy-targets.csv \
    --min-capacity 20 --limit 500
  ```

  This queue is a work list, not a claim that the missing capacity is addressable.
  A document must supply a usable apartment label and a resolvable BBL before it can
  create a unit record.

  Export the unit-label queue and import only reviewed labels:

  ```bash
  python3 tools/merges/export_unit_document_targets.py \
    --catalog-db /data/catalog.db \
    --out /data/unit-document-targets.csv \
    --min-capacity 2 --limit 500

  python3 tools/merges/import_unit_labels.py \
    --catalog-db /data/catalog.db \
    --csv /data/reviewed-unit-labels.csv
  ```

  The import CSV must contain `bbl`, `unit_label`, `source_ref`, `source_url`,
  and optionally `observed_at`. A count without a label is not importable.
- **Public DOF unit-address statements**: the official condo unit-lot table can be
  paired with the public DOF Statement of Account PDF endpoint. The miner keeps only
  the unit BBL, designation, property address, date, and source URL:

  ```bash
  python3 tools/merges/mine_dof_unit_addresses.py \
    --catalog-db /data/catalog.db \
    --condo-base-bbl 2039440003 \
    --out /data/parkchester-north-dof-addresses.csv
  ```

  This is a public-record address bridge, not a complete building roster by itself.
  A condo base BBL may cover many buildings; filter the extracted property address
  before importing any labels into the canonical catalog. The downloaded tax bills
  are not retained.
- **Exact-address ACRIS unit pass**: ACRIS property-legals rows can be exported for
  one street address and joined back to DOF's official unit-lot table:

  ```bash
  python3 tools/merges/mine_acris_building_units.py \
    --borough 2 --block 3944 --street-number 9 \
    --street-name "Metropolitan Oval" \
    --address "9 METROPOLITAN OVAL" \
    --catalog-db /data/catalog.db \
    --out /data/9-metropolitan-oval-acris-units.csv
  ```

  This is a dated legal-record evidence export. It reports observed unit labels;
  it does not claim that an unobserved label does not exist.
- **Batch gap-target collection**: the same deterministic pass can collect a review
  corpus for the ranked gap queue without importing or interpreting anything:

  ```bash
  python3 tools/merges/mine_acris_gap_targets.py \
    --targets /data/pricefixed-finance-gap-targets.csv \
    --out /data/pricefixed-acris-gap-evidence.csv
  ```

  Rows retain the target BBL/address, unit-lot BBL, unit label, ACRIS document ID,
  observation date, query URL, and collection status. Failed or empty targets stay
  in the corpus for later review.
- **Prepare the review queue**: after collection, make a smaller ranked file for
  follow-up research or local-model triage. This does not change the catalog:

  ```bash
  python3 tools/merges/prepare_acris_review.py \
    --evidence /data/pricefixed-acris-gap-evidence.csv \
    --out /data/pricefixed-acris-unresolved.csv \
    --summary /data/pricefixed-acris-review-summary.json
  ```

The output keeps only targets without ACRIS unit rows and sorts them by unresolved
capacity. The summary reports counts by status, borough, and building class.

Validate the completed DOF address evidence before any catalog import:

```bash
python3 tools/merges/validate_dof_unit_addresses.py \
  --catalog-db /data/catalog.db \
  --input /data/pricefixed-dof-all-unit-addresses.csv \
  --accepted /data/pricefixed-dof-unit-addresses-accepted.csv \
  --rejected /data/pricefixed-dof-unit-addresses-rejected.csv \
  --summary /data/pricefixed-dof-unit-addresses-summary.json
```

This only checks provenance and official unit-lot membership. It does not write to
the catalog or treat a model result as a fact.

Classify every official unit lot as residential or nonresidential from Finance's
current bulk assessment roll before treating it as a home. This is much faster than
requesting one Statement of Account PDF per lot and excludes owners and assessment
values from the output:

```bash
python3 tools/merges/classify_dof_unit_lots_bulk.py \
  --input /data/all-dof-unit-lots-for-classification.csv \
  --output /data/dof-unit-lot-tax-classes.csv \
  --summary /data/dof-unit-lot-tax-classes-summary.json
```

The command uses the current final roll first, then checks Finance's historical
assessment table for unit lots that have since been dropped or renumbered. It is
evidence preparation only and makes no catalog writes.

Review the summary, then merge residential addresses and remove tax-class-4 lots
from the canonical homes table. The dry run is the default:

```bash
python3 tools/merges/merge_dof_unit_lot_classifications.py \
  --classifications /data/dof-unit-lot-tax-classes.csv \
  --addresses /data/pricefixed-dof-unit-addresses-accepted.csv \
  --catalog-db /data/catalog.db \
  --summary /data/dof-unit-lot-merge-summary.json

# Repeat with --apply after reviewing the counts.
```

Source documents and observations remain in the catalog when a lot is excluded;
only its resolved home identity is removed.

## Local-model extraction

Use the local Qwen server only after deterministic code has downloaded and text-
extracted a document. Create one JSON object per document in a JSONL input file:

```json
{"id":"dob-123-page-3","source_type":"dob_schedule_a","target_address":"123 EXAMPLE STREET","source_url":"https://example.test/doc.pdf","text":"... extracted page text ..."}
```

Run the serial, resumable extractor:

```bash
python3 tools/local_model/run_qwen_extraction.py \
  --input /data/dob-document-packets.jsonl \
  --output /data/dob-qwen-results.jsonl
```

It uses `http://100.78.191.106:8080/v1`, `mlx-community/Qwen3-14B-4bit`,
`max_tokens=1024`, and `temperature=0.2` by default. It writes the raw model
response alongside parsed JSON and never writes to the catalog. Identical source
text at the same address reuses a completed local result across related filing IDs.
Do not send raw documents to a cloud model.

Legacy DOB filings are a separate source covering borough-office, eFiling, and HUB
jobs since 2000. Collect them into their own checkpoint database, then export only
labels that are still absent from the catalog:

```bash
python3 tools/merges/mine_legacy_dob_description_units.py \
  --db /data/legacy-dob-description-units.db

python3 tools/local_model/export_dob_description_packets.py \
  --descriptions-db /data/legacy-dob-description-units.db \
  --catalog-db /data/catalog.db \
  --output /data/legacy-dob-description-packets.jsonl \
  --progress-source legacy_dob_descriptions \
  --dataset ic3t-wcy2 --id-field job_s1_no \
  --packet-prefix legacy-dob-description \
  --source-type legacy_dob_job_description
```

To make packets from downloaded PDFs, create a manifest with columns
`id,local_path,source_type,target_address,source_url`, then run:

```bash
python3 tools/local_model/build_document_packets.py \
  --manifest /data/dob-documents.csv \
  --output /data/dob-document-packets.jsonl \
  --skipped /data/dob-documents-skipped.jsonl
```

This uses local `pdfinfo` and `pdftotext`, emits one packet per text-bearing page,
and records scanned or unreadable PDFs for a later OCR pass.
- Same-street 2-family addresses: `merge_same_street_two_family.py` adds only the
  conservative subset where PLUTO says there are exactly two residential units
  and PAD has exactly two addresses on the same street. These are address-level
  dwelling candidates, not proven apartment labels. The broader PAD address-count
  rule is intentionally not used; downstream consumers should filter the
  `entity_matches` row to see the candidate status and confidence.
- NYS voter file — blocked on Paul filing the request.

## Completed since the citywide merge

- **ACRIS unit-legals backlog**: all 548,038 staged rows have now been processed.
  The final pass left no staged rows pending and added 3,549 net-new canonical units
  after deduplication. The writable staging copy and runner are local build artifacts;
  the original archive remains unchanged.

## Build artifacts

`extracted_addresses.csv` and `hierarchy.db` are reproducible intermediates, not
release artifacts. Keep them in the chosen work directory or regenerate them with the
runner. Publish only the versioned, payload-free data bundle described in
[`DATA.md`](../../DATA.md), with the source commit and input provenance in its manifest.
