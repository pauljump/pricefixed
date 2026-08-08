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
  --output /tmp/stuytown-unit-document-targets-all-sources.csv
```

## Next source to pursue

The next useful source is a unit-bearing occupancy document for a ranked target:
Certificate of Occupancy schedules, DOB I-cards, filed plans, or another public
document that names both the building address and apartment labels. A document
that supplies only a total count should be retained as capacity evidence, not
used to manufacture apartment rows.

