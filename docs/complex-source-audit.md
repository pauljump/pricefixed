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

The browser-assisted capture pass found an important identity check. The BIS
profile for `342 1 AVENUE` displays BIN `1082865`, block `972`, lot `1`, which
corresponds to BBL `1009720001`. The queue also contains a Peter Cooper Village
row for the same normalized address assigned to BBL `1009780001`. The capture
manifest marks that relationship `bbl_mismatch`; matching address text is not
allowed to override the BIS tax-lot identity. See
[`docs/dob-document-capture.md`](dob-document-capture.md) for the reproducible
workflow.

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

The legacy borough-office/eFiling DOB corpus is a distinct historical source,
so it was refreshed separately rather than counted as a duplicate of the DOB
NOW pass:

```bash
python3 tools/merges/mine_legacy_dob_target_descriptions.py \
  --targets /tmp/stuytown-unit-document-targets-all-sources.csv \
  --out /tmp/stuytown-legacy-dob-description-evidence.csv
```

This refresh queried the legacy corpus by each target BBL and then required an
exact normalized source address. It produced 400 observations for 36 of the
228 unresolved addresses, plus 192 explicit `no_exact_source_rows` records for
the remaining targets. None of the 400 observations contained an explicit
apartment label: 205 were generic/ambiguous descriptions and 3 had no usable
description. The source lane therefore adds dated negative/ambiguous evidence
but no canonical units to this queue. The raw descriptions and query URL remain
in the CSV for review.

## Targeted API results

The bounded passes on 2026-08-08 produced the following evidence summary:

| Pass | Result |
| :--- | :--- |
| ACRIS exact-address unit rows over all 228 unresolved addresses | 228 `no_unit_rows`; 0 unit labels |
| DOB job descriptions over the 228 unresolved addresses | 11 exact-address observations across 5 addresses; 0 explicit labels, all ambiguous construction/mechanical descriptions |
| DOB job descriptions over the full 358-address footprint | 737 observations, including 681 explicit candidates across 115 addresses; no new explicit labels for the 228-address unresolved queue |
| Legacy DOB descriptions over the 228 unresolved addresses | 400 observations across 36 addresses; 0 explicit labels; 192 targets had no exact source rows |
| BIS C/O certificates for BIN 1082886 / target 627 East 14 Street | 11 certificates; certificate faces identify 629 East 14 Street / BIN 1082771 and expose no apartment labels |
| BIS C/O certificates for BIN 1082869 / target 272 First Avenue | 23 certificates; section-level addresses and apartment counts, 0 apartment identities |
| BIS C/O certificates for BIN 1082884 / target 535 East 14 Street | 2 certificates; section-level apartment counts, 0 apartment identities |
| BIS C/O index for BIN 1082864 / target 312 First Avenue | No certificates on file |
| BIS C/O certificates for BIN 1082885 / target 521 East 14 Street | 5 certificates; 2 exact section-level records, 3 identity/garage conflicts, 0 apartment identities |
| BIS C/O certificate for BIN 1082858 / target 18 Stuyvesant Oval | 1 certificate; section-level apartment counts, 0 apartment identities |
| BIS C/O certificate set for BIN 1082857 / target 12 Stuyvesant Oval | 28 of 49 files captured; all reviewed files have section-level counts and 0 apartment identities; remaining 21 blocked by BIS/Akamai access denial |

The DOB description API is therefore exhausted for the current unresolved
footprint. Its positive rows remain useful dated observations, but they do not
fill the queue. The next source attempt must retrieve a unit-bearing occupancy
document or equivalent address-specific primary record through BIS/DOB NOW
manual review; building counts and the existing description candidates do not
justify copying a floorplan or completing the roster by pattern.

### Browser-captured BIS certificate check

On 2026-08-08, the browser-assisted workflow captured the four public
certificates listed for BIN `1082865` from the BIS C/O index. All four are
two-page image-only scans. The local Apple Vision OCR pass was used only to
locate identity and unit-bearing language; the original PDFs remain the source
evidence.

| Certificate | Finding | Catalog result |
| :--- | :--- | :--- |
| `M000034595.PDF` | `330 First Avenue`, block 972 lot 1; building/unit categories and apartment counts, no apartment labels | shared-BBL capacity evidence only |
| `M000035795.PDF` | `330 First Avenue` / `400-410 East 20th Street`, block 972; counts and `Units 1, 2, & 3`, no apartment labels | shared-BBL capacity evidence only |
| `M000040059.PDF` | `400-410 East 20th Street` / `320-45 First Avenue`, block 972 lot 1; counts and `Units 1, 2, & 3`, no apartment labels | shared-BBL capacity evidence only |
| `M000028093.PDF` | scanned face says `332 First Avenue`, block 951 lot 3, conflicting with the BIS header for BIN 1082865 (`330 1 Avenue`, block 972 lot 1) | identity conflict; rejected |

No canonical units were added. The 228-address unresolved queue is unchanged:
these documents contain building-level occupancy information, not
address-specific apartment identities. The fourth certificate also validates
why document-level identity checks are required even after the BIS index has
supplied a BIN and BBL. Capture details and the OCR sidecar workflow are in
[`docs/dob-document-capture.md`](dob-document-capture.md).

The next duplicate-controlled capture for target `348 1 AVENUE` queried BIN
`1083680` on Peter Cooper Village BBL `1009780001`. Its C/O index named
`350 FIRST AVENUE`; both listed certificates were older business-use scans
whose faces identified different premises/block references and contained no
apartment labels. This BBL-level pass also added no units. The durable source
references and checksums are recorded in
[`docs/bis-1083680-capture.md`](bis-1083680-capture.md).

An additional queue-integrity check for `351 1 AVE` found a direct BBL
conflict: BIS identifies BIN `1020541` as block 926 lot 38 (`1009260038`),
while the unresolved queue assigned the address to the Peter Cooper Village
anchor BBL `1009780001`. No document was queried under the incorrect BBL; the
row is recorded as `bbl_mismatch` in
[`docs/bis-1020541-profile-check.md`](bis-1020541-profile-check.md).

For `352 1 AVE`, BIN `1083679` is on the queued BBL `1009780001`, but its C/O
index names `350 1 AVENUE`. Four captured certificates, including a 2021
temporary C/O, report 114 dwelling units and occupancy-use counts but no
apartment labels. They remain shared-BBL capacity observations; the result is
recorded in [`docs/bis-1083679-capture.md`](bis-1083679-capture.md).

The next distinct BIN, `1083683` for `400 E 23 ST`, listed three older C/O
scans. Their faces identified different business premises and block references
and supplied no apartment labels. No units were added; the capture record and
checksums are in [`docs/bis-1083683-capture.md`](bis-1083683-capture.md).

The separate DOB NOW public portal was also checked by BIN for `1083679`. It
exposed one approved Schedule of Occupancy request with 21 floor/use rows, but
no apartment labels in the public grid; the schedule detail remained in a
loading state during capture. This is a second occupancy/count lane, not a new
unit source. See [`docs/dob-now-schedule-1083679.md`](dob-now-schedule-1083679.md).

### HPD historical image-card capture

The HPD Online historical-card API was then exercised for the same Peter Cooper
Village anchor. Building ID `576` corresponds to `350 1 Avenue`, block 978 lot
1, BBL `1009780001`, and exposes one public card: `Icard_606251.pdf`, dated
`02/15/2008`. The card was retrieved through the public document endpoint and
OCR-reviewed locally. It is a nine-page historical classification/occupancy
record: it contains the exact premise and BBL plus dated apartment totals
(`114`, `116`, and `119` appear on different cards), but no apartment labels
tied to individual premises. It therefore adds traceable building history and
capacity evidence, not canonical units. The capture, checksum, and reproducible
retrieval command are in [`docs/hpd-icard-606251-capture.md`](hpd-icard-606251-capture.md).

The reusable capture command is:

```bash
python3 tools/merges/capture_hpd_historic_images.py \
  --building-id 576 \
  --out-dir /tmp/pricefixed-hpd-capture/576 \
  --doc-id 3594781
```

This opens a distinct HPD document lane for ranked targets. It preserves the
raw card list, original PDF bytes, source identifiers, retrieval time, and
checksum; it deliberately does not parse or import apartment labels.

The first BBL-wide HPD inventory for `1009780001` returned 21 building IDs and
18 historical cards. All 18 PDFs (93 pages) were captured and OCR-reviewed;
three buildings had no card available. The cards repeat building-level
classification and apartment totals, while their visible `UNIT` fields are
blank form fields. No individual apartment labels were found and no units were
added. The full mapping and checksums are in
[`docs/hpd-icard-pcv-bbl-1009780001-capture.md`](hpd-icard-pcv-bbl-1009780001-capture.md).

The independent Stuyvesant Town BBL `1009720001` was then queried separately.
HPD returned 46 building records, 28 records with 29 cards (177 pages), and 18
records without a card. Several captured cards contain `Unit #1`, `Unit #2`,
`Unit #3`, or unit ranges, but these are building/occupancy-section identifiers
paired with apartment totals, not individual apartment labels. The API also
returned duplicate/legacy records and addresses outside the target footprint;
they were retained as separate observations and not applied to the 228-address
queue. No canonical units were added. The inventory and review are recorded in
[`docs/hpd-icard-stuyvesant-bbl-1009720001-capture.md`](hpd-icard-stuyvesant-bbl-1009720001-capture.md).

The next distinct Stuyvesant Town BIN, `1082880` for `447 EAST 14 STREET`,
returned three older BIS certificates. One certificate was an identity conflict
for an unrelated Manhattan premise; one exact certificate named the target
premise and BBL but described `UNIT #2` with seven/eight apartments per story;
the third exposed five numbered building sections and no exact address in OCR.
Those `UNIT` values are building-section identifiers, not apartment labels. No
units were added. The PDFs, checksums, and parser regression are recorded in
[`docs/bis-1082880-capture.md`](bis-1082880-capture.md).

The following distinct BIN, `1082883` for `505 EAST 14 STREET`, returned three
older certificates. Two explicitly identify 505–515 East 14th Street, block 972
lot 1; all three describe numbered building sections and per-floor apartment
counts rather than individual apartment labels. No units were added. Capture
details and checksums are in [`docs/bis-1082883-capture.md`](bis-1082883-capture.md).
