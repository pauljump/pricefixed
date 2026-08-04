# NYC source audit

Pricefixed is trying to name real homes, not turn every housing-related number into
an apartment. A row can add a home only when an official record gives us both a
building identity and a usable unit label. Counts, floors, rooms, offices, and model
guesses do not pass that test.

## What we checked

On August 3, 2026, we pulled the public schemas for 2,396 datasets in the NYC Open
Data catalog. We reviewed fields containing words such as `apartment`, `unit`,
`suite`, `description`, `comments`, and `details`. We then tested plausible housing
sources against live records and the current catalog.

The reproducible pass found 34 unit-like field candidates with a building identity.
It also sent marker-count queries to 112 datasets that had both a building identity
and a text-like field. All 112 queries completed; 37 had at least one marker hit.
Those hits were either added to a source-specific collector or assigned one of the
exclusion reasons below after live value and parser checks.

Anyone can refresh that inventory without a model:

```bash
python3 tools/merges/audit_nyc_open_data_fields.py \
  --out-dir /data/nyc-source-audit

python3 tools/merges/audit_nyc_unit_text_markers.py \
  --inventory /data/nyc-source-audit/nyc-datasets.json \
  --output /data/nyc-source-audit/unit-text-marker-counts.jsonl
```

The inventory is a lead list. A matching field name is not proof that it names a
home. Every source still needs a source-specific rule and a direct BBL or a unique
official address match.

## Sources that name homes

The current build uses these kinds of evidence:

| Evidence | Examples | Rule |
|---|---|---|
| Official unit fields | HPD violations and problems, NYCHA inspections, evictions, DOB jobs and permits | Keep compact dwelling labels tied directly to a BBL. Reject common areas, floors, and commercial labels. |
| Official condo records | Digital Tax Map, CONDO_AREA, DOF assessment rolls | Keep residential unit lots and their official designations. Do not turn commercial, parking, or storage lots into homes. |
| Legal and sale records | ACRIS, DOF rolling and annualized sales | Keep an explicit apartment label tied to the property record. Preserve the document or sale reference and date. |
| Agency description text | DOB jobs, permits, violations, ECB and OATH cases, electrical records, Limited Alteration Applications, DCP housing projects, HPD work orders and blank-unit violation text, Landmarks complaints | Parse only labels attached to an apartment, dwelling-unit, or residential-unit marker. Send still-missing candidates to local Qwen, then require verbatim evidence before merge. |
| Address and capacity spine | PAD and PLUTO | Use official addresses and residential capacity to organize buildings and measure gaps. A capacity count does not create named units. |

[`release_sources.json`](release_sources.json) is the exact allowlist used by the
public exporter. Each accepted observation keeps its source name, source record,
URL, observed date when available, method, and match reason.

## Things that look useful but are not unit labels

| Dataset or field | What it actually contains | Decision |
|---|---|---|
| DOB Complaints `unit` | DOB office or processing codes such as `MAN.`, `QNS.`, `ELEVR`, and `PLUMB` | Excluded |
| Asbestos Control `acm_unit` | Measurement units such as square feet and linear feet | Excluded |
| Certificates of Occupancy | Existing or proposed dwelling-unit counts, not apartment labels | Counts only |
| Bedbug reports and housing lotteries | Building-level unit counts and bedroom distributions | Counts only |
| Fire inspection `inspecting_unit_code` | The fire company or inspecting team | Excluded |
| DCWP, license, storefront, and service-directory suite fields | Business or mailing locations, not a roster of homes in the target building | Excluded |
| DOB facade comments | Owner or applicant mailing addresses in the rows tested | Excluded |
| 311 service requests | Building complaints without a public apartment field | Building events only |
| DOB after-hours `enclosed_work` | A boolean flag | Excluded |
| BSA project descriptions and DOB safety violations | Housing counts or generic project language; no deterministic apartment labels in the live marker audit | No new units |
| Elevator safety data | Building device records, not apartment identities | Building evidence only |

## What remains out of reach

- DOB Certificate and Schedule of Occupancy documents can contain floor-by-floor
  detail, but unattended retrieval from the public portal is blocked by its Akamai
  layer. The bulk datasets expose counts only.
- Most one- and two-family homes never produce apartment-level HPD records. The NYS
  voter file may help, but it requires a formal request and is not part of this open
  data run.
- A missing label is not proof that a home does not exist. The catalog reports what
  an official source has actually named and keeps capacity gaps visible.

New source proposals are welcome. A useful contribution includes the dataset ID,
the exact field, a direct building join, sample records, and a rule that avoids
creating homes from counts or mailing addresses.
