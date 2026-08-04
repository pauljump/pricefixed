# Pricefixed data contract

Pricefixed has two public surfaces:

1. This repository is the reproducible collector and catalog builder.
2. A future versioned release asset will be the supported way to consume a citywide
   catalog snapshot.

The repository does not currently distribute a citywide snapshot. In particular,
the local `catalog.db` used for the July 31, 2026 build is a 14.7 GB working database
and is intentionally not committed to Git. Do not treat a count in project
documentation as a downloadable dataset.

## Current build, not a release

The current working build contains:

| measure | count |
|---|---:|
| canonical units | 2,750,889 |
| buildings | 948,147 |
| observations | 7,181,360 |
| official condo unit lots | 306,603 |
| anonymous PLUTO capacity slots | 3,753,223 |

"Canonical unit" means the project has retained a source-supplied unit label and
resolved it to a BBL under the documented matching policy. It does not mean every
home exists in the catalog, that every source statement is correct, or that the unit
is addressable on a multi-address tax lot. See [`CATALOG.md`](CATALOG.md).

## Release format

Each public snapshot should be attached to a GitHub Release, rather than committed to
the repository. Its asset bundle should include:

| file | purpose |
|---|---|
| `manifest.json` | release ID, generation time, row counts, file checksums, and software commit; source freshness is in `sources.csv` |
| `quality-report.json` | catalog counts, coverage, source mix, evidence mix, match methods, open gaps, and release warnings |
| `units.csv` | one canonical unit record per `(BBL, normalized unit label)` |
| `unit_observations.csv` | source-attributed observations resolved to those units, with resolution method and confidence |
| `sources.csv` | source name, source kind, and collection methodology |
| `source-policy.json` | exact source allowlist and review scope used for the release |
| `catalog.db` (optional) | full SQLite database for provenance and advanced analysis |

The exporter defaults to [`release_sources.json`](release_sources.json). It exports a
unit only when at least one resolved observation comes from a source in that policy,
and exports only those supporting observations. Archive-only and listing-feed-only
identities stay in the local research catalog unless their sources are reviewed and
deliberately added to the policy.

CSV files are UTF-8 with a header row and RFC 4180-compatible quoting. The exporter
does not publish `source_documents.payload` or `observations.raw_fields`; those fields
may contain bulky or source-specific material and are not part of the stable public
release interface.

## Stable fields

`units.csv`

```text
unit_id,bbl,unit_label,normalized_unit,first_seen,last_seen
```

`unit_observations.csv`

```text
unit_id,observation_id,source,source_ref,observed_at,observation_kind,address,unit_label,bedrooms,bathrooms,price,status,evidence_grade,resolution_confidence,resolution_method,matched_at
```

`sources.csv`

```text
source,source_kind,methodology,first_seen,last_seen
```

Fields may be added in a later release. Existing field names and meanings will not be
silently repurposed. Consumers should join observations to units using `unit_id`, not
an address string or display unit label.

## Create a release bundle

From a completed local catalog build:

```bash
python3 catalog_export.py --db /path/to/catalog.db --out pricefixed-catalog-YYYY-MM-DD \
  --release-id YYYY-MM-DD --commit "$(git rev-parse HEAD)"
python3 catalog_report.py --db /path/to/catalog.db --out pricefixed-catalog-YYYY-MM-DD/quality-report.json \
  --release-id YYYY-MM-DD --commit "$(git rev-parse HEAD)"
python3 catalog_verify_release.py pricefixed-catalog-YYYY-MM-DD
```

These commands create the three CSV files, `source-policy.json`, `manifest.json`, and
`quality-report.json`. Review the manifest and quality report, compress the directory,
publish it as a GitHub Release asset, and link that release from the README. Do not
publish a snapshot until its source licenses, freshness, and checksums have been
reviewed.

## Querying SQLite directly

SQLite is the complete form of the catalog. The public relationship is:

```text
units <- entity_matches <- observations -> sources
```

Only `entity_matches` rows with `entity_type = 'unit'` and `status = 'resolved'` join
an observation to a canonical unit. Keep `resolution_method`,
`resolution_confidence`, and `evidence_grade` in downstream analyses; dropping those
fields turns a source-attributed catalog into an unsupported assertion.

## Known boundaries

- PLUTO residential counts are a denominator, not an apartment roster.
- A BBL can cover multiple premises. A canonical unit is not necessarily an
  addressable apartment without separate premise evidence.
- Pricefixed preserves reported asking prices and public-record observations; it does
  not claim a reported price is a lease transaction or a market-wide rent measure.
- A release must name its build date. Live feeds and public datasets change over time.
