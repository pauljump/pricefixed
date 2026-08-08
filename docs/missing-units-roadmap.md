# Missing Units Roadmap

This is the handoff point before location-based inference. The broad, easy source
passes are complete for the current build; the items below are the remaining source
and coverage work, not claims that inferred homes have already been added.

Current local build: **3,044,550 canonical units** against NYC's **3,705,000**
housing-stock benchmark, leaving about **660,450** homes that are counted by the city
but not yet named in the catalog.

This is the source order for the remaining gap:

1. **NYS voter file**: likely the best citywide source for apartment labels in
   one- and two-family homes that do not create much HPD/DOB/ACRIS trail.
2. **Small-building logic after voter-file review**: use voter-file address/unit
   patterns to decide what can be inferred as a hypothesis, and what still needs a
   primary source before it can become canonical.
3. **ACRIS property legals and staged evidence**: useful for condos, co-ops, sales,
   mortgages, and specific buildings with legal unit references.
4. **DOB occupancy documents**: Certificates of Occupancy, Schedules of Occupancy,
   I-cards, and plans for ranked high-capacity gaps. This is targeted document
   retrieval, not a clean citywide API.
5. **DOF unit-address bridges**: Statements of Account and tax-bill evidence for
   official unit lots where the address/unit link is still ambiguous.
6. **Listing and history archives**: landlord feeds, broker archives, and public
   historical listings. Good for units that were marketed; weak for quiet
   owner-occupied homes.

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
