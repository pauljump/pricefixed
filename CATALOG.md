# The Pricefixed Catalog

`pricefixed` is building an evidence-backed catalog of NYC housing. The goal is not
to make an unsupported claim that every apartment is already known. The goal is to
make every incorporated claim traceable, keep uncertainty visible, and make coverage
accumulate as new primary material arrives.

The citywide reporting denominator is **3,705,000 housing units** (NYC's 2023
housing-stock benchmark). `catalog.py --status` reports this separately from `units`
and `evidenced_unit_coverage`; it must never turn an unobserved housing unit into a
canonical record merely to improve the percentage.

For complete count coverage, `--materialize-capacity-slots` creates one anonymous
slot per imported PLUTO `units_res` position. A slot is a source-derived cardinality
position, not an apartment identity, addressable unit, or substitute for evidence.

When a full PLUTO spine is imported, status also reports `pluto_residential_unit_capacity`
and the named-unit evidence rate against it. PLUTO's `units_res` is a building-level
count, not an apartment roster; it creates a coverage denominator, never anonymous
canonical apartments.

## Current citywide build

The current citywide build has **3,753,223 anonymous capacity slots** across the
city. This is the complete count layer currently supported by the imported primary
PLUTO records, and exceeds the 3,705,000 reporting benchmark because the two sources
measure housing stock differently. It has **3,044,550 canonical units** with a
source-supplied label and resolved BBL: **82.2% of the 3,705,000 housing-stock
reporting denominator** and 81.1% of the imported PLUTO capacity. These numbers are
intentionally reported separately: a capacity slot answers "how many units does this
source say the building has?"; a canonical unit answers "which apartment did a
source identify?"

This is a working build, not yet a published data release. Its counts are reported so
the methodology can be audited; downstream consumers should use a versioned release
asset and manifest once one is published. [`DATA.md`](DATA.md) defines that interface.

To build or resume the count layer after importing PLUTO:

```bash
python3 catalog.py --db catalog.db --materialize-capacity-slots --slot-batches 500
```

The command checkpoints by BBL after each 1,000-building batch. Re-running it is
idempotent and resumes from `capacity_slot_progress` until the count matches PLUTO.

## The contract

Every datum passes through four distinct layers:

```text
primary source material -> source observation -> entity resolution -> catalog record
```

They must not be conflated.

For physical identity, the catalog distinguishes a tax lot from an addressable
premise. A BBL can cover several physical addresses, so a resident-facing unit is
only addressable when its source address exactly matches PAD on that BBL:

```text
BBL/tax lot -> official premise address -> normalized unit label
```

`derive_addressable_units` builds this layer from already retained observations. It
does not assign a BBL-only label to an arbitrary address on a multi-address lot.

- **Primary source material** is what a landlord, brokerage, agency, or public record
  actually published. Store its unmodified payload, source reference, and retrieval
  time when available.
- **Observation** is a time-stamped statement from that source: a listing advertised a
  given price, or an agency recorded a permit. Observations are append-only evidence,
  not the current truth.
- **Entity resolution** is Pricefixed's own claim that an observation refers to a
  building or unit. It records its method, confidence, rationale, and status.
- **Catalog record** is a stable entity assembled from resolved observations. It never
  replaces the underlying source material.

## Canonical hierarchy

```text
BBL (official NYC tax-lot identifier)
  -> building
    -> official address
      -> unit
        -> source-attributed observations over time
```

BBL is the initial public geography spine. A unit is only created after a listing
resolves to exactly one BBL and contains a usable unit label. A current listing is not
proof that every unit in a building exists, and a building's `units_res` count is not a
unit roster. The catalog keeps those distinctions explicit.

## Resolution policy

The first implementation uses one intentionally strict rule:

1. Normalize the listing address and imported official address.
2. Resolve it only when that normalized address maps to exactly one BBL.
3. Normalize the listing unit label.
4. Create the canonical unit from `(BBL, normalized unit label)` only when both are
   present.

Everything else is retained as an observation with an `unresolved` or `ambiguous`
match. Under-matching is preferable to silently joining two people's homes together.
When an exact address maps to multiple official BBLs, every candidate is retained in
`entity_match_candidates`; no candidate becomes the match until additional independent
evidence resolves it.

The current reconciliation rule is intentionally narrow: an ambiguous listing resolves
only when an HPD violation has already confirmed the same normalized unit label at the
same normalized address on exactly one candidate BBL. The linked HPD observation is
retained in `entity_match_evidence` for review. Run it after importing direct official
evidence:

```bash
python3 catalog.py --source hpd_violations --boro MN --db catalog.db
python3 catalog.py --reconcile-candidates --db catalog.db
```

## Evidence grades

- `source_document`: a raw upstream payload was captured with the observation.
- `legacy_snapshot`: a historical price snapshot from the pre-catalog listing store.
  It has source, source reference, date, and price/terms, but no historical raw payload.

This is a limitation of earlier data capture, not something the catalog should hide.

## Run it

First build the existing source databases, then assemble the catalog:

```bash
python3 build_record.py --source pluto --limit 5000 --db record.db
python3 scrape.py --source stuytown --db listings.db
python3 catalog.py --record record.db --listings listings.db --db catalog.db
```

Add direct HPD unit evidence without relying on the aggregated building-event store:

```bash
python3 catalog.py --source hpd_violations --boro BX --limit 1000 --db catalog.db
```

The HPD importer preserves each agency row and creates a unit only for a direct BBL
plus a non-common-area apartment label. A violation is evidence that HPD associated a
unit with an enforcement event, not evidence of a complete building roster.

HPD Open Market Order charges are a second direct unit-observation source. They record
agency work orders and contain a stable work-order ID, BBL, street address, and
apartment field:

```bash
python3 catalog.py --source hpd_omo_work_orders --boro BX --limit 1000 --db catalog.db
```

They can establish that HPD associated a specific apartment label with a BBL at a
particular time. They do not establish occupancy, current condition, or a full roster.

ACRIS Real Property Legals adds historical legal-index observations for Manhattan,
Brooklyn, Queens, and the Bronx. Its `good_through_date` is preserved as a source
snapshot date, not misrepresented as a recording date:

```bash
python3 catalog.py --source acris_property_legals --boro MN --limit 1000 --db catalog.db
```

For citywide identity acquisition, use the separate `acris_unit_legals` lane. It asks
the official index only for rows where the source's `unit` field is populated; its
offsets are therefore not interchangeable with an unfiltered ACRIS scan. Each legal
row gets its own provenance key, including when a document names multiple apartments
on one BBL:

```bash
python3 acquire.py --db /path/to/catalog.db --source acris_unit_legals --keyset --page-size 1000 --pages 1
```

The cursor is the lowest `document_id` in the prior page. Boundary documents are
included again (`<=`) and deduplicated by the source-row key, preventing skipped
apartments when one ACRIS document contains many legal rows. Use `--cursor VALUE`
only to bootstrap a catalog that previously used the offset lane.

For an exhaustive raw-source pull on storage separate from the catalog, stage the
same official rows first. The stage database keeps unmodified JSON payloads and its
own durable cursor; it never claims staged rows are canonical apartments:

```bash
python3 acris_stage.py --db /path/to/acris-source.db --page-size 10000 --pages 1

# Resolve a bounded staged batch into the canonical catalog later.
python3 catalog.py --source acris_stage --stage-db /path/to/acris-source.db --limit 1000 --db catalog.db
```

### Archived Vayo unit evidence

`all_nyc_units.db` is an archived secondary aggregation, not an authoritative
housing-stock source. It can contribute a retained BBL, address, unit label, and
the archive's `source_systems` metadata. Its rows are stored verbatim as archive
documents. Rows explicitly marked `TEXT_MINED_*` remain unresolved leads; they do
not create canonical or addressable units. PLUTO capacity is never updated from
this archive.

The importer stores a keyset checkpoint in `archive_import_progress` in the same
transaction as each page, so the command is resumable without remembering a
cursor. `--cursor` is only for a documented replay or recovery start.

```bash
python3 catalog.py --source vayo_all_nyc_units --vayo-db /path/to/all_nyc_units.db --limit 25000 --db catalog.db
python3 catalog.py --demote-vayo-text-mined --db catalog.db
```

The demotion command is idempotent. It preserves raw archive observations and
removes a claimed canonical unit only when no other resolved source supports it.

Vayo's separate StreetEasy archive is imported independently because it has a
different schema. It retains the source building URL and dated unit-history row;
the importer creates a unit only after the archived street address matches PAD.

```bash
python3 catalog.py --source vayo_streeteasy_unit_summary --vayo-db /path/to/se_listings.db --limit 10000 --db catalog.db
```

Vayo's Elliman MLS archive contains historical listing data. Its importer retains a
minimized provenance payload (stable listing ID, address/unit, dates, price/status,
and MLS identifier) and intentionally excludes archived broker contact fields. A
unit is canonical only after its normalized address uniquely matches PAD.

```bash
python3 catalog.py --source vayo_elliman_mls_archive --vayo-db /path/to/elliman_mls.db --limit 25000 --db catalog.db
```

Vayo's Corcoran archive is ingested independently with the same PAD-only unit
resolution and PII-minimized provenance policy. It retains listing identifiers,
address/unit, price/status, dates, and non-contact listing metadata, while
excluding agent/contact and detail JSON fields.

```bash
python3 catalog.py --source vayo_corcoran_archive --vayo-db /path/to/corcoran.db --limit 10000 --db catalog.db
```

Additional direct public unit-observation imports:

```bash
# DOF sales: BBL, sale date/price, and apartment number when reported. The
# importer also accepts a narrow, explicit apartment suffix after the final
# comma in the official address field, which DOF uses for some co-op sales.
python3 catalog.py --source annualized_sales --boro MN --limit 1000 --db catalog.db

# Current DOF rolling sales: derives BBL from official borough/block/lot fields.
python3 catalog.py --source rolling_sales --boro MN --limit 1000 --db catalog.db

# NYC DOI executed residential possession events since 2017. Marshal names are not stored.
python3 catalog.py --source evictions --boro BX --limit 1000 --db catalog.db

# DOB NOW job filings: selective apartment/condo labels from filing locations.
python3 catalog.py --source dob_now_jobs --boro MN --limit 1000 --db catalog.db

# DOB NOW approved permits: a separate dated permit record with apartment/condo labels.
python3 catalog.py --source dob_now_permits --boro MN --limit 1000 --db catalog.db

# DOB NOW Certificates of Occupancy: building-level certificate and dwelling-count evidence.
# This source never creates apartment rows because it has no apartment-label field.
python3 catalog.py --source dob_now_certificates --boro MN --limit 1000 --db catalog.db

# OSE's dated short-term-rental registration/listing spreadsheet.
python3 catalog.py --source ose_str_snapshot --snapshot /path/to/STR.xlsx --snapshot-date 2026-01-07 --db catalog.db

# HPD registered-rental coverage denominator. Omit --limit for a complete scope run.
python3 catalog.py --source hpd_registration_coverage --boro BX --db catalog.db
```

These sources are event evidence, not tenant histories or apartment rosters. In
particular, eviction events must never be displayed as a judgment about a tenant or
owner, and DOB job labels do not prove that unmentioned units do not exist.

For citywide sources, use bounded acquisition pages. Each completed page records its
source, scope, requested offset, returned row count, and canonical-unit count before
and after the page in `acquisition_pages`:

```bash
python3 acquire.py --db /path/to/catalog.db --source hpd_problems --page-size 250 --pages 1
python3 acquire.py --db /path/to/catalog.db --source rolling_sales --page-size 250 --pages 1
python3 acquire.py --db /path/to/catalog.db --source acris_unit_legals --keyset --page-size 1000 --pages 1
```

Do not run two acquisition writers against the same SQLite database at once. Resume a
source/scope without `--offset`; use an explicit offset only to begin a documented
backfill range. For a one-off import where aggregate status is slow, pass
`--no-status` to `catalog.py`.

DOF condominium unit tax lots are a separate official identity layer:

```bash
python3 catalog.py --source condo_units --limit 1000 --db catalog.db
```

This imports `UNIT_BBL` into `official_unit_lots`; it does not create a physical
catalog unit or relabel `CONDO_BASE_BBL` as a building billing BBL.

Add PAD alternate addresses for the ZIPs represented in the listing inventory:

```bash
python3 catalog.py --source pad_addresses --zips 10001,10002 --limit 10000 --db catalog.db

# Citywide PAD backbone (uses materially more storage than a ZIP-scoped pass).
python3 catalog.py --source pad_addresses --all-addresses --db catalog.db
```

PAD adds official address-to-BBL evidence only. Re-run the base listing import afterward
to resolve more existing listing observations against those addresses.

After PAD and direct observations are present, derive addressable premise units in
bounded batches. This is required for multi-address tax lots: it keeps `3 Peter
Cooper Rd, 1F` distinct from a possible `7 Peter Cooper Rd, 1F`.

```bash
python3 catalog.py --source derive_addressable_units --limit 10000 --derive-batches 1 --db catalog.db
```

The command advances `addressable_unit_progress`; rerun it until no new observation
batch remains. It creates a unit only when the source address exactly matches PAD on
the resolved BBL, and keeps BBL-only labels out of the addressable roster.

For the entire active inventory footprint, derive the ZIP scope automatically and then
measure current listing resolution:

```bash
python3 catalog.py --source pad_listing_zips --listings listings.db --db catalog.db
python3 catalog.py --record record.db --listings listings.db --db catalog.db
python3 catalog.py --coverage --listings listings.db --db catalog.db
```

## Inference is not identity

Repeated listing and agency observations may eventually show a floor pattern or an
apparent missing adjacent unit. Record that as a **unit hypothesis** with its supporting
observations and confidence, never as a canonical unit. A hypothesis becomes a unit only
when an independent primary source confirms a BBL plus unit label.

`catalog.db` contains `sources`, `source_documents`, `buildings`, `addresses`,
`units`, `observations`, `entity_matches`, candidate BBLs, and audit links from a
resolution to its corroborating evidence. The source databases remain intact.

## Coverage-growth passes

The August 7, 2026 local build reached **3,044,550 canonical units**. The last local
Qwen mining run added **21,121 net-new units** from public official-description
queues and parser-delta checks, then passed the repo's test suite (`150 tests`).
The largest additions were:

- LAA official descriptions: **13,612** net-new units.
- HPD violation descriptions where the apartment field was blank: **6,420** net-new units.
- Description parser deltas across already-mined public records: **1,087** net-new units.
- Landmark complaint descriptions: **2** net-new units.
- NYCHA blank and elevator-application queues: **0** net-new units in this run.

The local model output was accepted only after deterministic candidate checks:
source row IDs had to match the packet, model output had to carry the current
fingerprint/status shape, evidence had to appear verbatim in the source text, and
the proposed unit label had to be one of the deterministic candidates. Partial
Antigravity/Gemini sidecar output was not merged into the trusted catalog.

## Coverage-growth pass (2026-07-30/31)

A working citywide build (not committed here — see
[`tools/merges/README.md`](tools/merges/README.md)) went from 514,306 to 2,750,889 canonical units, 12.4% to
74.3% of the 3,705,000 citywide target. Six scripts under `tools/merges/`: raw
archive extraction, exact-match BBL resolution with a condo-designation tiebreak,
merging real (non-synthetic) archive evidence, single-family whole-building
inference, a residential-vs-non-residential tiebreak for remaining ambiguous
addresses, and a direct pass over DOF's own condo unit-lot registry. Full
methodology, what didn't work and why (bulk CofO data has no unit labels; PAD
address-count is not a safe proxy for unit count on 2-family lots), and what's left
(the ACRIS staging backlog, the NYS voter file) are documented there.

## What comes next

This establishes the method, not complete inventory coverage. The next additions are:

1. Use the NYS voter file only if a current file is already lawfully downloadable;
   do not spend project time on a formal request unless that decision changes. See
   [`docs/missing-units-roadmap.md`](docs/missing-units-roadmap.md).
2. Add direct unit observations from property-specific DOB occupancy documents and
   other public document series that contain an apartment label plus a resolvable BBL.
3. Capture raw source documents on every scrape going forward, including price-history
   snapshots, so all new history receives `source_document` evidence grade.
4. Record neighboring-unit patterns only as hypotheses with supporting evidence; do
   not upgrade them to canonical units until a primary source confirms BBL + label.
5. Publish catalog coverage as counts and freshness by source, never as an invented
   completeness percentage.

## Checkpoint before location logic

The broad, easy public-record mining pass is closed at the August 7, 2026 build. The
trusted catalog contains only source-backed unit labels; no neighboring-unit or
building-count inference was used to inflate the 3,044,550 total. The next location
logic phase should start from this committed state, produce hypotheses separately,
and merge a new unit only when an independent source confirms its BBL and label.

## Exhaustion map

The public-source frontier currently falls into three lanes:

- **Bulk, direct unit evidence (implemented):** listings; HPD violations and work
  orders; filtered ACRIS property legals; DOF annualized sales; residential eviction events;
  DOB NOW job filing apartment labels. Each provides a BBL plus a source-supplied
  label only for events it records.
- **Bulk building/count context:** PLUTO and HPD Multiple Dwelling Registrations can
  measure the residential tax-lot and registered-rental-building universe. Their
  `unitsres`/registration fields are denominators and diagnostics, never unit rosters.
  DOB NOW Certificates of Occupancy add another official building-level count and
  certificate history, but still do not identify individual apartments.
  `hpd_registration_coverage` stores an immutable run with `partial` status when
  capped and joins its BBLs to PLUTO context already imported into the catalog.
- **Targeted public document retrieval:** BIS/DOB NOW Certificates of Occupancy,
  Schedules of Occupancy, I-cards, and plans can resolve individual high-value gaps,
  but the portal does not provide a citywide bulk apartment-label API. Queue these by
  BBL/job only where catalog evidence conflicts or a count gap warrants review.

NYS HCR apartment rent-registration histories are not an eligible general source:
they are confidential to the tenant, owner, or authorized representative. Historical
landlord availability feeds may be imported when publicly accessible and captured with
their raw source document, but web archives and inferred neighboring units remain
evidence or hypotheses, not canonical identity.
