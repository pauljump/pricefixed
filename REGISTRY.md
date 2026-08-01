# Pricefixed NYC Housing Registry

Pricefixed is building an open registry of NYC housing that can support public
asking-rent history and, eventually, analysis of coordinated pricing behavior. The
registry is not a claim that NYC publishes a complete apartment roster. It reconciles
the city records that do exist and leaves missing identity explicit.

## Registry v0.1

The first public release is a **tax-lot capacity and identified-unit registry**. It
contains every imported residential BBL, official address records, source-backed unit
identities, and anonymous residential capacity where an official source reports a
count without a unit roster.

It does not claim that every capacity position has a unique street address or apartment
label. A BBL may cover several physical premises, and a unit label on a BBL is not
always a premise-addressable home.

## Public entity layers

```text
building (BBL)
  -> official address
    -> premise, when the evidence supports a physical address
      -> identified unit, when a source supplies a usable label
  -> unresolved dwelling capacity, when a source supplies only a count
```

Each release must preserve these distinctions. The current catalog stores the first
four layers as `buildings`, `addresses`, `premises`, `units`, and
`housing_capacity_slots`; source observations and entity matches explain why a record
exists.

## Identity statuses

Public release tables will expose an identity basis rather than treating all rows as
equivalent:

| status | meaning |
|---|---|
| `official_unit_lot` | An official unit-level property record identifies the unit. |
| `direct_observation` | A public source supplied an address/unit label and the catalog resolved it. |
| `derived_single_dwelling` | An explicit rule identifies a one-dwelling building without inventing an apartment label. |
| `derived_resolution` | A documented, deterministic rule resolved otherwise ambiguous public evidence. |
| `capacity_only` | An official source reports a dwelling count, but does not identify an individual home. |
| `ambiguous` | Evidence exists but cannot safely resolve to one entity. |

The exact source, matching method, confidence, and evidence grade remain available in
the observation and match tables. `capacity_only` and `ambiguous` records must never
be presented as named homes.

## Contribution contract

A contribution may add a source, a rule, a correction, a benchmark, or release
tooling. Any contribution that changes public identity must include:

1. A public source or dataset identifier and its terms.
2. A deterministic transformation or matching rule.
3. The identity status and confidence it creates.
4. A positive fixture and a case the rule must reject.
5. A description of its coverage and likely failure modes.

This makes a claim reviewable without requiring a reviewer to download the full
citywide database.

## Release standard

Every registry release has a date, source commit, manifest, checksums, data dictionary,
quality report, and a small sample bundle. The supported consumer files are defined in
[`DATA.md`](DATA.md). The complete SQLite database is optional provenance material;
payload-free CSV or Parquet exports are the normal analysis interface.

## What we need next

1. Materialize and validate the citywide premise layer from imported official addresses.
2. Promote BBL-level unit labels to premise-level identities only where the evidence
   supports that assignment.
3. Publish method-level coverage and error metrics for every release.
4. Keep unresolved capacity visible as the work queue, rather than filling it with
   inferred apartment labels.
