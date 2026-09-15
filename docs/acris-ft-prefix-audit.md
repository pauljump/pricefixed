# ACRIS `FT_` document-prefix audit

**Checked:** 2026-08-08  
**Dataset:** [NYC Open Data ACRIS Real Property Legals](https://data.cityofnewyork.us/resource/8h5j-fqxa.json)  
**Query shape:** non-empty `unit`, `document_id` beginning with `FT_`, descending document ID, inclusive keyset boundary

## Result

The ACRIS feed has a legacy-looking `FT_` document-ID namespace. It is easy to
mistake this for a missing source partition because the normal stage cursor is a
numeric document ID. A bounded prefix scan was run with the new `--document-prefix
FT_` mode and wrote 3,688 unique raw payloads across 1,963 document IDs. The API
returned repeated boundary rows between pages; the immutable payload hash made the
replay idempotent.

The duplicate-work audit then checked the existing external build artifacts:

- `/Users/mini-home/pricefixed-build/acris-unit-source-working.db` already contains
  all 3,688 `FT_` rows, and all are marked resolved.
- `/Users/mini-home/pricefixed-build/catalog.db` already contains the corresponding
  ACRIS observations and unit matches.
- Therefore this lane adds **zero new canonical units**. No rows were merged a
  second time.

## Code change

`acris_stage.py` now accepts `--document-prefix FT_` and stores its cursor under a
separate keyset source (`acris_unit_legals:prefix=FT_`). This makes namespace
refreshes explicit and prevents a future prefix scan from overwriting or sharing a
cursor with the ordinary numeric scan. It does not turn a prefix into a canonical
unit source by itself: normal ACRIS label validation and BBL/address provenance
still apply during catalog resolution.

## Reproducibility

```sh
env PYTHONPATH=. python3 acris_stage.py \
  --db /tmp/acris-ft-unit-source.db \
  --document-prefix FT_ \
  --page-size 1000 \
  --pages 10
```

The raw stage is intentionally outside the repository. The committed code and
test cover the cursor namespace and idempotent boundary behavior; the external
stage/build databases remain diagnostic artifacts and were not modified.

