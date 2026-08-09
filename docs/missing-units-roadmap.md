# Missing Units Roadmap

This is the handoff point before location-based inference. The broad, easy source
passes are complete for the current build; the items below are the remaining source
and coverage work, not claims that inferred homes have already been added.

Current local build: **3,052,376 canonical units** against NYC's **3,705,000**
housing-stock benchmark, leaving about **652,624** homes that are counted by the city
but not yet named in the catalog.

This is the source order for the remaining gap:

1. **NYS voter file**: likely the best citywide source for apartment labels in
   one- and two-family homes that do not create much HPD/DOB/ACRIS trail.
2. **Small-building logic after voter-file review**: use voter-file address/unit
   patterns to decide what can be inferred as a hypothesis, and what still needs a
   primary source before it can become canonical.
3. **ACRIS property legals and staged evidence**: useful for condos, co-ops, sales,
   mortgages, and specific buildings with legal unit references. The `FT_` document
   namespace was separately refreshed and duplicate-checked on 2026-08-08; it was
   already fully staged/resolved and added no new units. Remaining ACRIS work is
   targeted gap resolution, not another blind citywide replay.
4. **DOB occupancy documents**: Certificates of Occupancy, Schedules of Occupancy,
   I-cards, and plans for ranked high-capacity gaps. This is targeted document
   retrieval, not a clean citywide API.
5. **DOF unit-address bridges**: Statements of Account and tax-bill evidence for
   official unit lots where the address/unit link is still ambiguous.
6. **Listing and history archives**: landlord feeds, broker archives, and public
   historical listings. Good for units that were marketed; weak for quiet
   owner-occupied homes.

### DOF unclassified-unit fallback audit

The current DOF assessment classification left 1,099 official condo unit lots as
`tax_class_not_found`. A bounded historical check queried those exact BBLs in the
official `kevu-8hby` assessment table for 2015, 2016, and 2017. It produced 3,297
review rows, all `no_historical_match`, with zero historical residential tax-class
matches. The audit output is `/tmp/dof-unclassified-historical-audit.csv`; the
reproducible tool is:

```bash
python3 tools/merges/audit_dof_unclassified_unit_lots.py \
  --input /data/dof-unit-lot-tax-classes-final.csv \
  --out /tmp/dof-unclassified-historical-audit.csv \
  --summary /tmp/dof-unclassified-historical-audit-summary.json \
  --years 2015,2016,2017
```

These lots remain unresolved. The official condo designation alone is not enough
to classify a home when the current assessment roll and historical fallback both
lack a tax-class record.

### DOF direct unit-lot backlog and Statement-of-Account follow-up (2026-08-09)

The direct DOF condo unit-lot pass was completed without replaying prior
observations. It added **7,698** canonical units from official unit-lot BBLs with
non-empty DOF designations. The catalog retained **34,113** prior direct
observations whose rows were already classified or otherwise resolved, and withheld
11 remaining non-unit designations (`RM`, `UNIT`, `APT`, `SUITE`, and `*`). The
capacity layer did not change. The merge is now idempotent: it skips an existing
`dof_condo_unit_lots_direct` observation instead of trying to create a duplicate or
discarding its prior classification.

The targeted Statement-of-Account checks did not provide a new canonical roster:

- Condo base BBL `3072790231` returned 480 address-bearing rows, but all were
  outside the named-unit layer after the existing tax-class review; none were
  imported as units.
- Bases `1000510014` and `4050100028` returned 174 and 157 rows respectively
  without an address (`No data found` on the sampled public PDFs); none were
  imported.

These results are retained as bounded source-audit evidence, not converted into
building-wide identities. The existing
[`tools/merges/merge_dof_unit_lot_classifications.py`](../tools/merges/merge_dof_unit_lot_classifications.py)
remains the canonical Statement-of-Account bridge for validated residential
address/unit observations.

The high-capacity ACRIS check for `9 METROPOLITAN OVAL` found 68 distinct exact
address labels, all already present in the catalog; net-new was zero. No duplicate
ACRIS import was performed.

### DOF Statement-of-Account property-address bridge

The deterministic merge at
[`tools/merges/merge_dof_unit_lot_classifications.py`](../tools/merges/merge_dof_unit_lot_classifications.py)
handles validated DOF Statement-of-Account rows only when the unit-lot BBL and
unit designation already exist in `official_unit_lots` and the same BBL/unit
identity already exists in the catalog. It adds the statement's exact property
address as a bridge and records the public source URL, statement date, raw
extraction method, and resolved addressable-unit link. An address by itself is
rejected and cannot create a canonical unit.

The merge writes rejected candidates and a JSON summary, making accepted and
rejected populations auditable without silently broadening the catalog.

### NYC Open Data schema refresh (2026-08-09)

The deterministic `audit_nyc_open_data_fields.py` inventory was refreshed against
the live NYC Open Data catalog and compared with the August 3 source audit. It found
2,396 datasets, 87 unit-field candidates, and 34 building-unit candidates. There
were zero new unit-bearing or building-unit candidate dataset IDs. The only new
description candidate was a donations-comments field and is unrelated to housing.
The ACRIS, DOB, HPD, eviction, and other housing datasets surfaced by the inventory
are already in the source map and prior mining passes. This lane is therefore
closed for now; rerunning the full catalog scan without a changed schema or dataset
is duplicate work.

Reproducible refresh command:

```bash
python3 tools/merges/audit_nyc_open_data_fields.py \
  --out-dir /tmp/pricefixed-open-data-audit.nVQLKA \
  --page-size 1000
```

### Bozzuto SecureCafe browser capture (2026-08-09)

The official Bozzuto NYC rentals index was checked property by property. The
official pages for 19 Dutch, Aalto57, and 88 Leonard link to public SecureCafe
availability tables. Plain HTTP requests receive a Cloudflare challenge, but the
browser-visible tables expose exact current unit labels. A bounded capture recorded
24 rows, all with the exact source address, unit label, rent, square feet, and
availability text:

- 19 Dutch St: `30H`, `49H`, `48H`, `48F`, `59E`, `60F`, `29E`, `63F`,
  `14I`, `40C`, `38D`, `25B`.
- 1065 2nd Ave: `06F`, `09F`, `23C`, `08H`.
- 88 Leonard Street: `0503`, `0712`, `PHB-5`, `2002`, `1507`, `1123`,
  `1214`, `0516`.

The importer is [`tools/merges/import_securecafe_browser_capture.py`](../tools/merges/import_securecafe_browser_capture.py).
It accepts only explicit browser-visible rows and preserves the raw row, official
property URL, availability URL, retrieval time, and capture metadata. It never
expands floorplans or building counts. Official DOB NOW job-filing crosswalks
resolved the three exact premises to BBLs `1000780047` (19 Dutch), `1013307502`
(1065 2nd Ave), and `1001730027` (88 Leonard). The crosswalk is stored as separate
evidence rather than silently treating a BBL-wide label as address-specific.

The final import produced 24 resolved listing observations and **11 net-new
canonical units**; 13 labels already existed through other source paths. The
catalog therefore moved from 3,044,550 to **3,044,561** without changing the
anonymous PLUTO capacity layer. The current vacancies are evidence of named units,
not a complete building roster. Riverbank and The Ludlow exposed only counts or
floorplans in this check and were not expanded.

Raw HTML capture hashes for the reproducibility handoff:

- 19 Dutch: `4e502046b1382c6d3a4b4565de8eb2a7d9608ac7e031324364034b1aa9039b49`
- Aalto57: `eee415a3109e51f71154645b2d209e0446481c1a9dfe9e91e88d7aa093848417`
- 88 Leonard: `ca1930a4e01dfca2a8b8aea7e82619dc34300aa4dbee955da4ab72ca034ecc0f`

The capture manifest and raw HTML are staged under `/tmp` for this run; the
catalog retains the row payload and official crosswalk evidence in `source_documents`.

### Rockrose official selected listings (2026-08-09)

Rockrose's official residential index exposes 13 NYC building pages with a
server-rendered `SELECT LISTINGS` section. The deterministic Rockrose adapter
[`pricefixed/adapters/rockrose.py`](../pricefixed/adapters/rockrose.py) collected
46 explicit unit cards; it did not expand the building descriptions, floorplans,
or unit counts. The captured rows were:

| Official premise | Explicit units | BBL evidence |
|---|---:|---|
| 41 River Terrace | 1 | `1000160210` |
| 200 Water Street | 3 | `1000750001` |
| 180 Ashland Place | 4 | `3020950026` |
| 43-10 Crescent Street | 7 | `4004350013` |
| 47-05 Center Blvd | 7 | `4000210060` |
| 43-25 Hunter Street | 1 | `4004337501` |
| 43-22 Queens Street | 7 | `4002660003` |
| 43-12 Hunter St | 3 | `4004340016` |
| 410 W 53rd Street | 1 | `1010620019` |
| 555 W 38th St | 3 | `1007100001` |
| 100 Jane Street | 1 | no matching DOB NOW filing; catalog address resolver retained |
| 110 Horatio Street | 4 | `1006420004` |
| 666 Greenwich Street | 4 | `1006040033` |

The official page HTML was fetched with the source URL and page SHA-256 retained in
each raw listing payload. DOB NOW exact-address queries supplied one BBL for 45 of
the 46 premises; 42 of those crosswalks matched an already-imported official
address and were stored as separate `official_address_bbl_crosswalk` observations.
All 46 listing observations resolved, but only **36 were net-new canonical units**;
10 labels already existed through other sources. These are current selected listings,
not a complete Rockrose roster.

### Greystar public property JSON (2026-08-09)

Greystar's official public search was queried through the Coveo-backed endpoint
used by its website, then each returned property was checked through the official
`/api/property/<id>` JSON endpoint. Five-borough filtering retained only properties
whose API location city is New York, Brooklyn, Queens, Bronx, or Staten Island.
The run checked 22 public NYC property records. Only property `21037` (345 East
94th Street, BBL `1015570025`) exposed explicit `availableUnits` rows: `12F`,
`25D`, `15F`, `PHG`, `19F`, `11F`, `06D`, and `21G`. The other checked properties
exposed no unit-bearing rows and were not expanded from floorplans.

The reproducible adapter is [`pricefixed/adapters/greystar.py`](../pricefixed/adapters/greystar.py).
Each row preserves the official property JSON, the public search URL, the property
API URL, retrieval time, exact address, and explicit `availableUnits` record. The
catalog import produced 8 resolved observations and **1 net-new canonical unit**;
the remainder were already represented by prior source paths. This is current
vacancy evidence, not a complete Greystar roster.

### UDR official apartment JSON-LD (2026-08-09)

UDR's official New York City apartments index links five public
`apartments-pricing` pages. Their JSON-LD `itemListElement` records contain
explicit apartment labels, pricing, bedrooms, bathrooms, square feet, and
unit-specific URLs. The bounded run found 23 rows at 808 Columbus Avenue. The
reproducible adapter is [`pricefixed/adapters/udr.py`](../pricefixed/adapters/udr.py).

The source address is retained in each raw payload while the street premise is
used for resolution. PAD has multiple BBL rows for this normalized address, so
the adapter queries official DOB NOW filings and carries the unique exact-address
crosswalk to BBL `1018527501`. The catalog import produced 23 resolved
observations and **19 net-new canonical units**; four labels already existed from
other sources. The adapter rejects JSON-LD entries that lack an explicit apartment
label and never turns a floorplan or count into a unit.

### Rudin public property/listing JSON (2026-08-09)

Rudin's official availability page loads the public
[`/api/properties-json`](https://www.rudinresidential.com/api/properties-json)
endpoint. The response keeps property records separate from explicit `Listing`
records. The adapter joins a listing only to its parent property's exact
`field_address`, and requires an active listing record with an apartment label;
property records, floorplans, and missing-address records are rejected.

The bounded pull returned 29 current rows across the Rudin portfolio. Each raw
payload preserves the complete official property and listing records, the page
URL, API URL, and retrieval time. Importing these rows produced **2 net-new
canonical units**; the remaining labels were already present through other
source paths. This is current vacancy evidence, not a complete Rudin roster.

### Related Rentals official NYC unit-detail pages (2026-08-09)

Related's official search returned 94 current New York City cards across eight
pages. The search cards describe floor-plan categories, so they were not treated
as apartments by themselves. Each linked detail page was fetched and accepted
only when its official `entity` record contained an explicit unit ID and its
property header contained an exact street address. The bounded run also queried
official DOB NOW filings by premise; 55 rows had a unique address→BBL crosswalk,
which is stored separately as `dob_now_job_filings` evidence.

The reproducible adapter is [`pricefixed/adapters/relatedrentals.py`](../pricefixed/adapters/relatedrentals.py).
It retained 94 explicit unit-detail observations and added **45 net-new
canonical units** after catalog deduplication. The remaining labels were already
represented or remain unresolved where the address maps to multiple BBLs. This
is current vacancy evidence, not a complete Related Rentals roster.

### Mirador public GraphQL availability (2026-08-09)

Pan Am Equities' official availability navigation points to Mirador Real Estate's
public properties page. Its public Luxury Presence GraphQL feed returned 45 active
records in the bounded pull; four were Connecticut records and were excluded, and
41 NYC records were retained. The adapter
[`pricefixed/adapters/mirador.py`](../pricefixed/adapters/mirador.py) accepts a row
only when `addressLine1` contains an unambiguous street premise plus an apartment
label. It preserves the stable API ID, exact listed address, detail URL, complete
API record, query variables, and retrieval timestamp. Building descriptions,
counts, and floorplans are not expanded.

The 41 rows cover 20 premises. Official DOB NOW queries produced unique BBLs for
15 premises, covering 35 rows; those crosswalks are stored as separate evidence.
The catalog import resolved 37 of 41 listing observations, left three ambiguous
and one unresolved, and added **5 net-new canonical units**, moving the build from
3,044,673 to **3,044,678**. This is current vacancy evidence, not a complete
Mirador or Pan Am roster.

### LeFrak City public Spherexx unit options (2026-08-09)

LeFrak City's official availability page exposes two public AJAX responses:
`getpropertybuildinglist.asp` identifies available building options and
`getpropertyunitlist.asp` identifies explicit unit options. The bounded pull
returned `8D` at `97-28 57th Avenue` (Panama) and `4B` at `97-30 57th East
Avenue` (United States). The official [LeFrak building directory](https://www.lefrakcity.com/buildings/)
supplied those exact premises; the adapter does not turn the portfolio's
building count, floorplans, or option patterns into additional units.

The two rows were imported as current vacancy observations with their raw option
HTML, stable `data-unit-id`, source URLs, retrieval timestamp, and an independent
DOB NOW address crosswalk retained in `raw_json`. The public options did not
provide reliable rent, bedroom, bathroom, or square-foot fields, so those remain
null. This is a current-vacancy feed, not a complete LeFrak roster.

## NYS voter file lane

Use this lane only if a voter file is already lawfully downloadable or if Paul later
decides to request it. Do not spend project time on a formal-request workflow unless
that decision changes.

As of the August 7, 2026 check, no clean, current, public NYC voter file with
street/apartment fields was found. The NYC Open Data voter-analysis file is
anonymized and geographic only. Search results point to BOE request/licensed access
or stale PDFs, not a current machine-readable public download.

If this lane is reopened, New York State Board of Elections says requests for
voter-registration data must be made through its FOIL process and must include a
statement that the data will be used for an elections purpose. The BOE page also
says statewide files are large, delivered as zipped comma-delimited ASCII, and come
with a file layout.

Request only what the catalog needs:

- Active NYC voter-registration records.
- Residential address fields, including apartment/unit fields when present.
- County/borough, city, state, ZIP, election district or other geographic fields
  needed to dedupe and audit address parsing.
- File layout/data dictionary.
- Exclude date of birth, phone, email, voting history, party enrollment, and any
  confidential/protected voter records if those fields are separable.

Do not publish raw voter records. Treat the file as restricted source material. The
only catalog output should be aggregated, source-attributed unit evidence:

- normalized address
- normalized unit label
- county/borough
- source batch/date
- count of distinct voter records supporting that address/unit
- no names
- no individual voter identifiers

## Draft request text

```text
I am requesting the current New York City voter-registration file for academic
research and election-related public research purposes under New York State Election
Law Section 3-103(5).

Please provide active voter-registration records for Bronx, Kings, New York, Queens,
and Richmond counties in the standard zipped comma-delimited ASCII format, together
with the file layout/data dictionary.

The research purpose is to study residential address normalization and apartment-unit
coverage in New York City election records, including how apartment/unit fields are
represented across the five NYC counties. The project will not use the records for
commercial solicitation or any non-election purpose.

If available as separable fields, please include residential street address,
apartment/unit, city, state, ZIP, county, election district, assembly district, senate
district, congressional district, and registration status. If available as separable
fields, please exclude date of birth, phone number, email address, voting history,
party enrollment, and records protected by confidential voter status.

If any requested field is not available or cannot be separated from the standard file,
please provide the standard voter-registration file layout and note the limitation.
```

## After receipt

1. Store the raw file outside the repository.
2. Save the file layout and request metadata in the build workspace.
3. Build an importer that reads only the address/unit fields needed for unit evidence.
4. Normalize addresses through the existing PAD/crosswalk path.
5. Keep only address/unit combinations with a resolved BBL and a real unit label.
6. Aggregate before any export; do not expose names or voter-level rows.
7. Merge only after a dry-run summary reports accepted rows, rejected rows, and common
   rejection reasons.

## NYCDB audit

`nycdb` was checked on August 7, 2026 as a coverage backstop. It is a strong source
map, but it did not reveal a new citywide apartment-roster dataset.

Datasets in `nycdb` with direct apartment/unit fields:

| NYCDB dataset | Unit-bearing field | Pricefixed status |
| :--- | :--- | :--- |
| `hpd_complaints` / HPD complaints and problems | `Apartment`, with `UnitType` and `SpaceType` | Already mined to completion through `hpd_problems`, filtered to `unit_type = 'APARTMENT'`, then merged through the compact public-unit pass. |
| `hpd_violations` | `Apartment` | Already mined and merged. |
| `hpd_charges` / OMO charges | `Apartment` | Already mined through HPD OMO direct field and description passes. |
| `executed_evictions` / `marshal_evictions` | `EvictionApartmentNumber`, `apt` | Already mined with privacy-minimized payloads; marshal names are excluded. |
| `dobjobs` / DOB NOW jobs and permits | `AptCondoNos` | Already mined through direct compact fields and description passes. |
| `dof_sales` / `dof_annual_sales` | `ApartmentNumber` | Already mined through DOF sale imports. |
| `dof_property_valuation_and_assessments` | `Aptno`, `CoopApts`, `Units` | Already mined for assessment unit labels; count fields stay denominators. |
| `acris` real/personal property legals | `UNIT` | Already mined/staged; exact-address backlog remains useful for targeted gaps. |

Datasets in `nycdb` that have addresses or counts but do not name individual homes:

- PLUTO current and historical versions: official address and `UnitsRes`, but no
  apartment roster.
- DOB Certificates of Occupancy bulk files: dwelling-unit counts, not apartment labels.
- HPD AEP, CONH, LL44, underlying conditions, litigations, jurisdiction, rent-stab,
  MCI, J-51, 421-a, Furman Center SHD: useful building/count context, not unit labels.
- OCA housing court: public case/address context, but the `oca_addresses` schema in
  `nycdb` does not expose a street/unit field suitable for canonical unit creation.
- DOB complaints `unit`: DOB processing/office codes, not apartment labels.

Conclusion: after the existing compact public-unit, official-description, DOF,
ACRIS, and archive passes, `nycdb` mainly confirms the remaining gap is not another
obvious NYC Open Data apartment field. The next productive non-voter work is ranked
gap targeting: large unresolved capacity via ACRIS/DOB/DOF documents, and separate
logic for one-address two-family homes.
