# StuyTown / Peter Cooper Village source audit

This is a source audit, not a unit roster. It records what public pages can
establish and what they cannot.

Audit date: 2026-08-08

## Public sources checked

| Source | What it publishes | How Pricefixed should use it |
| :--- | :--- | :--- |
| [StreetEasy: Peter Cooper Village](https://streeteasy.com/complex/peter-cooper-village) | Complex facts, a building list, current listings, and historical listing activity | Keep explicit address/unit labels as dated listing observations. Do not treat the page's floorplan count or complex total as an apartment roster. |
| [StreetEasy: 3 Peter Cooper Road](https://streeteasy.com/building/3-peter-cooper-road-new_york) | Individual listing labels such as `#5D`, plus a partial listing history when available | Import only the address and unit label shown on the individual listing/page. The page does not expose a complete list of all units. |
| [NYBits: Peter Cooper Village](https://www.nybits.com/apartments/c_peter_cooper_village.html) | A named 21-building PCV list and building-level figures such as 15 floors and 119 units | Use as count and footprint corroboration. It is not sufficient to create 119 canonical unit rows for any building. |
| [Beam Living / StuyTown availability](https://www.stuytown.com/nyc-apartments-for-rent/) | Current advertised availability and links to individual unit pages | Use the existing StuyTown adapter/feed for dated listing observations. Individual availability is not evidence that unadvertised apartments do not exist. |

## What this establishes

- Public pages corroborate that Peter Cooper Village is a named 21-building
  complex and publish useful building-level counts.
- Public listing pages can add individual unit labels when a listing is
  available or a historical row is exposed.
- Public pages do **not** provide a complete, stable, address-specific roster
  for every apartment in the complex.

## What this does not establish

The following are not canonical apartment identities by themselves:

- `119 units` or any other building-level count.
- A floorplan catalog or a number of floorplans.
- A repeated floor/line pattern copied from another building.
- A unit label observed only at the shared BBL level when the tax lot contains
  multiple addresses.

The catalog therefore keeps building capacity, BBL-wide labels, exact-address
labels, and listing observations in separate fields and tables.

## Current local result

The deterministic all-source pass is complete for the local packet and catalog
material. For the 358-address StuyTown/PCV footprint it found:

- 130 addresses with direct address-level unit evidence.
- 228 addresses still needing a direct unit-bearing document or equivalent
  address-specific primary source.

Those remaining addresses are in the generated document-target queue. Rebuild
the queue from the reproducible local outputs with:

```bash
python3 tools/merges/export_complex_unit_document_targets.py \
  --evidence /tmp/stuytown-unit-evidence-all-sources.json \
  --out /tmp/stuytown-unit-document-targets-all-sources.csv
```

## Next source to pursue

The next useful source is a unit-bearing occupancy document for a ranked target:
Certificate of Occupancy schedules, DOB I-cards, filed plans, or another public
document that names both the building address and apartment labels. A document
that supplies only a total count should be retained as capacity evidence, not
used to manufacture apartment rows.

The DOB NOW/BIS handoff is currently a manual review step: DOB's public guidance
directs users to search the portal by address or BIN, and the agency documents
that DOB NOW has no external API for this workflow. The target CSV is therefore
an acquisition queue, not a claim that the documents were downloaded. After a
reviewer transcribes labels, the import CSV must include `address`, `bbl`,
`unit_label`, `source_ref`, and `source_url`:

```bash
python3 tools/merges/import_unit_labels.py \
  --catalog-db /data/catalog.db \
  --csv /data/reviewed-unit-labels.csv
```

Create a manual review worksheet with exact-address BIS links, the BBL building
map, and the DOB NOW public-portal entry point:

```bash
python3 tools/merges/export_dob_document_review_queue.py \
  --targets /tmp/stuytown-unit-document-targets-all-sources.csv \
  --out /tmp/stuytown-dob-document-review-queue.csv
```

The 2026-08-08 run produced 228 review rows and 0 unparseable addresses. The
worksheet deliberately leaves `unit_label`, `document_url`, and
`exact_address_match` blank for human review; no document is treated as
evidence until those fields are filled from the source itself.

The importer rejects BBL-only rows and rows whose document address is not an
exact official catalog address on that BBL. It writes those rejected rows to
`<input>.rejected.csv` and creates both the BBL-wide source observation and the
addressable premise/unit link for accepted rows.

ACRIS can be used as an unattended evidence pass for the same queue:

```bash
python3 tools/merges/mine_acris_gap_targets.py \
  --targets /tmp/stuytown-unit-document-targets-all-sources.csv \
  --out /tmp/stuytown-acris-gap-evidence.csv
```

The collector preserves the complex target fields and checkpoints by exact
`(BBL, address)`, so shared-BBL addresses are never skipped or conflated.

DOB NOW job descriptions are a separate direct-evidence lane. The targeted
collector filters to jobs with no direct apartment field, keeps only exact
source-address matches, and emits the verbatim description plus deterministic
parser result:

```bash
python3 tools/merges/mine_dob_target_descriptions.py \
  --targets /tmp/stuytown-unit-document-targets-all-sources.csv \
  --out /tmp/stuytown-dob-description-evidence.csv
```

Rows marked `explicit_candidate` are review candidates, not automatically a
complete roster. Rows marked `ambiguous_description` remain visible without a
unit label and cannot create a canonical unit.

## Targeted API results

The bounded passes on 2026-08-08 produced the following evidence summary:

| Pass | Result |
| :--- | :--- |
| ACRIS exact-address unit rows over all 228 unresolved addresses | 228 `no_unit_rows`; 0 unit labels |
| DOB job descriptions over the 228 unresolved addresses | 11 exact-address observations across 5 addresses; 0 explicit labels, all ambiguous construction/mechanical descriptions |
| DOB job descriptions over the full 358-address footprint | 737 observations, including 681 explicit candidates across 115 addresses; no new explicit labels for the 228-address unresolved queue |

The DOB description API is therefore exhausted for the current unresolved
footprint. Its positive rows remain useful dated observations, but they do not
fill the queue. The next source attempt must retrieve a unit-bearing occupancy
document or equivalent address-specific primary record through BIS/DOB NOW
manual review; building counts and the existing description candidates do not
justify copying a floorplan or completing the roster by pattern.
