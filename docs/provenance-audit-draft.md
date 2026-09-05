# NYC Housing Catalog: Provenance & Sourcing Audit Draft

## 1. Summary

Pricefixed is building an open, reproducible catalog of New York City housing units directly from public records and landlord availability feeds.

The goal is to create a public unit registry for NYC where every single row is traceable back to an official government filing, public permit, legal document, or verified listing source. In real estate data, mystery rows and black-box aggregations are the norm. Pricefixed operates on a different rule: if we claim a housing unit exists at an address, we must be able to point to the exact public record or source observation that proves it.

This document outlines the current state of provenance for the citywide catalog: where the data comes from, what has been extracted across various mining and merging passes, how data sources contribute to the unit hierarchy, what limits currently exist in our base catalog, and how future contributors can add new sources responsibly.

Current local build as of August 7, 2026:

| Measure | Count |
| :--- | ---: |
| Canonical units | 3,044,550 |
| Addressable units | 578,978 |
| Buildings | 1,147,182 |
| Addresses | 2,193,923 |
| Observations | 7,977,231 |
| Resolved unit observations | 5,418,176 |
| Unresolved unit observations | 2,172,515 |
| Official condo unit lots | 306,607 |
| Anonymous PLUTO capacity slots | 3,753,223 |

The broad, easy source-mining phase is closed at this checkpoint. The trusted build
does not use neighboring-unit or building-count inference to manufacture canonical
rows. The remaining checklist below is release and provenance hardening; location
logic is a separate follow-on phase and must keep hypotheses distinct from confirmed
units.

---

## 2. Source Categories

The project ingests public records across several major government datasets and commercial listing feeds. Each source category contributes specific pieces of the unit hierarchy (tax lot, address, or apartment label):

*   **NYC PAD / Address Base**: NYC Department of City Planning Property Address Directory. Provides the official street address base, BBL (Borough-Block-Lot) tax-lot mappings, and building identification numbers (BINs).
*   **DOF Unit Lots / Property Assessment**: NYC Department of Finance tax records and condo unit-lot listings (such as datasets `8y4t-faws` and `yjxr-fw8i`). Establishes tax-class classifications (residential vs. non-residential) and official condo unit identifiers across tax lots.
*   **DOF Statement / Account Style Sources**: NYC Department of Finance quarterly tax statements and property account records (`m8p6-tp4b`, `25th-nujf`). Contributes validated statement addresses for tax-lot units.
*   **DOB NOW Job Descriptions**: NYC Department of Buildings (DOB) NOW portal job applications. Contains narrative job descriptions describing floor layouts, unit subdivisions, and apartment additions.
*   **DOB Electrical Descriptions**: DOB electrical permit filings. Provides detailed descriptions of electrical work per apartment (e.g., meter pans, subpanels, wiring per specific unit label).
*   **DOB Approved Permits**: DOB permits granted for alterations, new buildings, and major renovations (`833y-fsy8`). Contains work descriptions referencing specific unit numbers and building layout changes.
*   **DOB Electrical Detail**: Granular DOB electrical work item records detailing room-by-room and unit-by-unit electrical installations.
*   **DOB Violations**: DOB notices of violation. Often cites specific illegal conversions, unpermitted alterations, or structural violations by unit number.
*   **OATH / ECB Violations**: Office of Administrative Trials and Hearings (OATH) and Environmental Control Board (ECB) summonses for building code infractions. Cites specific units in hearing decisions and enforcement records.
*   **HPD Violations**: NYC Housing Preservation and Development (HPD) housing maintenance code violations (`wvxf-yra5`). Contains direct apartment-level violation records tied to specific BBLs.
*   **HPD HWO / OMO Work Orders**: HPD Emergency Housing Work Orders (HWO) and Open Market Orders (OMO). Records agency-mandated emergency repairs and contractor work performed in specific units.
*   **DCP Housing Project Descriptions**: NYC Department of City Planning housing database and project description descriptions tracking development pipelines and unit counts.
*   **ACRIS / Property Legal Records**: NYC Automated City Register Information System (ACRIS) real property legals and unit deeds (`630x-zavq`). Records unit identifiers from legal conveyances, mortgages, and condo master deeds.
*   **Eviction & Compact Public Record Sources**: NYC Marshals eviction execution filings and housing court records. Identifies specific residential unit labels subject to legal process.
*   **Landlord & Availability Feeds**: Direct public availability feeds (RentCafe, AppFolio, Nooklyn, StuyTown, etc.) providing live asking rents and unit observations.

---

## 3. Merged Source Table

The table below summarizes the extraction, verification, and merge passes recorded in the local build merge summaries (`*-merge-summary.json`).

| Source / Pass Name | Input Rows | Verified Unique Units | Net-New Units | Catalog Writes (1/0) | Short Description & Source Meaning |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `dof-unit-lot-merge` | 306,603 unit lots | 258,487 w/ statement addr | 254,249 inserted/updated | 1 | DOF condo unit lots matched to statement addresses; removes non-residential units and populates official condo unit records. |
| `dof-unit-lot-historical-delta-merge` | 63 unit lots | 50 w/ official addr | 50 inserted/updated | 1 | Historical DOF assessment tax-lot delta pass resolving tax class shifts across assessment cycles. |
| `additional-official-description-laa-merge` | 14,669 | 14,566 | 13,612 | 1 | Unit labels extracted from LAA official-description records with deterministic candidate validation and local Qwen review. |
| `additional-official-description-hpd_violation_blank-merge` | 6,496 | 6,479 | 6,420 | 1 | HPD violation descriptions where the structured apartment field was blank, but the narrative contained a verified unit label. |
| `description-parser-delta-merge` | 9 queues | 1,719 | 1,087 | 1 | Parser-delta pass over already-mined official descriptions, reviewed by local Qwen and retained only with verbatim source evidence. |
| `legacy-dob-description-merge` | 16,523 | 10,437 | 9,815 | 1 | Deterministic & Qwen LLM extraction from legacy DOB job descriptions to discover unit labels in structural filings. |
| `dob-electrical-description-merge` | 14,655 | 10,722 | 10,346 | 1 | Unit label extraction from DOB electrical permit descriptions indicating dedicated meters/wiring per apartment. |
| `oath-dob-description-merge` | 4,036 | 3,292 | 2,982 | 1 | Extraction from OATH/ECB violation descriptions where code enforcement cited specific apartments. |
| `dob-description-expanded-merge` | 5,214 | 2,547 | 2,255 | 1 | Second-pass expanded DOB job description mining across additional alteration filings. |
| `ecb-dob-description-merge` | 2,456 | 2,169 | 1,773 | 1 | Extraction from ECB building violation narrative descriptions citing specific unit numbers. |
| `dof-assessment-unit-labels-merge` | 1,747 | 1,747 | 1,747 | 1 | Unit labels extracted from official Department of Finance property assessment roll records. |
| `hpd-hwo-description-merge` | 1,408 | 1,380 | 1,360 | 1 | Extraction from HPD Housing Work Order emergency repair narratives specifying targeted apartments. |
| `dob-approved-permit-description-merge` | 517 | 438 | 352 | 1 | Extraction from DOB approved permit work descriptions detailing specific unit alterations. |
| `dob-violation-description-merge` | 442 | 316 | 266 | 1 | Unit labels extracted directly from DOB notices of violation descriptions. |
| `hpd-omo-description-merge` | 223 | 216 | 202 | 1 | Unit labels extracted from HPD Open Market Order emergency contractor job descriptions. |
| `condo-area-merge` | 4 | 4 | 4 | 1 | Target area condo unit record reconciliations. |
| `additional-official-description-landmark_complaint-merge` | 2 | 2 | 2 | 1 | Landmark complaint descriptions with direct apartment-label evidence. |
| `dof-historical-assessment-merge` | 1 | 1 | 1 | 0 | Assessment roll unit label check against historical DOF files. |
| `dob-description-merge` | 6,243 | 3,218 | 0 | 1 | Initial baseline pass over DOB job descriptions (superseded by expanded pass for net-new units). |

The August 7 local-model run accepted only records that matched the current packet
fingerprint/status contract, kept the original source row ID, and supplied evidence
that appeared verbatim in the source text. A partial Antigravity/Gemini sidecar pass
was left out of the trusted catalog because it was incomplete and duplicated IDs.

---

## 4. Current Limitations

While the catalog currently indexes over 3.04 million canonical units, several provenance limitations must be addressed before open-source release:

1. **Base Catalog Provenance Audit Required**: The foundation of the current database was assembled from multiple high-volume public ingest steps (PLUTO, DOF tax lots, HPD registrations, and historical imports). While newer passes enforce strict row-level source tracking, parts of the legacy base catalog still lack explicit line-by-line lineage linking each unit to the exact source row that introduced it.
2. **Mixed Evidence Strength**: Units in the catalog currently range from strongly source-backed (e.g., backed by an active DOF tax-lot statement, ACRIS deed, or direct HPD violation) to weakly source-backed (e.g., inherited from an earlier bulk import or address-suffix parse).
3. **Inherited Base Rows**: Earlier build steps created canonical unit records that need retroactive labeling to indicate their originating dataset and extraction version.
4. **Target Provenance Standard**: Moving forward, the standard for this repository is strict reproducibility: **every address, unit label, and source relationship must be fully traceable to a primary public source or deterministic derivation script.** If a row cannot be traced to a verifiable source, it must be flagged or excluded from public distribution.

---

## 5. Contributor Guidance: Adding a New Source Responsibly

We welcome new public record sources and listing adapters, but all additions must meet strict provenance and safety standards. To add a new source to Pricefixed, contributors must document and supply the following:

### Requirements for New Sources

1. **Source URL & Dataset Identity**: Provide the exact URL, NYC Open Data dataset ID (e.g., `8y4t-faws`), or primary source endpoint.
2. **Fields Used**: List every column or field extracted (e.g., `house_number`, `street_name`, `unit_number`, `description_text`).
3. **Rationale**: Explain why the field reliably indicates a real housing unit rather than a commercial space, storage room, boiler room, or common area.
4. **False-Positive Risks**: Identify common failure modes in the raw data (e.g., "Unit 1" referring to "Phase 1", commercial store fronts labeled as "Store 1", or boiler room violations recorded as "BSMT").
5. **Validation Method**: Specify how unit labels are validated. Deterministic parsing (regex / rule-based string matching) is strongly preferred over non-deterministic model extractions. Any LLM-assisted extraction must use deterministic candidate verification against the raw source text.
6. **Expected Output Shape**: Document the exact output fields (BBL, BIN, normalized street address, normalized unit label, source dataset, source record ID).
7. **Evidence Examples**: Include at least 5 representative raw sample records along with their expected parsed canonical units.
8. **Required Tests & Checks**: Include unit tests under `tests/` demonstrating:
    * Exact string matching from raw description to extracted label.
    * Rejection of common non-residential patterns (e.g., `REAR`, `CELLAR`, `GARAGE`, `STORE`, `OFFICE`).
    * Idempotent ingestion (re-running the adapter does not duplicate records or overwrite higher-confidence data).

---

## 6. Release Audit Backlog

To bring the pricefixed codebase and dataset to a fully audited open-source release,
the following tasks remain. These are release tasks, not additional trusted unit
mining:

* [ ] **Base catalog source coverage audit**: Perform a full audit of all existing rows in `catalog.db` to tag un-sourced or legacy-imported units.
* [ ] **Source coverage table generation**: Create an automated script that outputs an exact breakdown of unit counts by primary source attribution.
* [ ] **Address coverage report**: Generate a comprehensive report comparing catalog addresses against NYC PAD to identify missing street blocks and BBLs.
* [ ] **Unit provenance report**: Build a tool to audit every canonical unit record and print its complete chain of supporting evidence (observations, permits, violations, tax filings).
* [ ] **Row-level source export**: Ensure exported CSV/Parquet releases include explicit `source_dataset` and `source_id` columns for every unit row.
* [ ] **Privacy & abuse guardrails**: Review listing and public record exports to ensure sensitive personal information (tenant names from private legal filings) is scrubbed or excluded while retaining public building/unit integrity.
* [ ] **Reproducible build instructions**: Document single-command end-to-end build workflows so third-party researchers can reproduce the full catalog from scratch.
* [ ] **Public release checklist**: Complete final verification steps (schema validation, checksums, hosting setup, and documentation review) prior to publishing public dataset downloads.
