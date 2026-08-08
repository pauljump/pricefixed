#!/usr/bin/env python3
"""Build a read-only address and evidence inventory for a managed complex."""
import argparse
import csv
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.engine.crosswalk import normalize_address
from pricefixed.engine.dedupe import normalize_unit


DEFAULT_PROPERTIES = ("Peter Cooper Village", "Stuyvesant Town")


def _chunks(values, size=500):
    values = list(values)
    for start in range(0, len(values), size):
        yield values[start:start + size]


def _catalog_indexes(connection, normalized_addresses):
    addresses = defaultdict(list)
    buildings = {}
    bbl_units = Counter()
    premises = defaultdict(list)
    for chunk in _chunks(normalized_addresses):
        placeholders = ",".join("?" for _ in chunk)
        for normalized, bbl, address, zipcode in connection.execute(
            f"SELECT normalized,bbl,address,zipcode FROM addresses WHERE normalized IN ({placeholders})",
            tuple(chunk),
        ):
            addresses[normalized].append({
                "bbl": bbl, "address": address, "zipcode": zipcode,
            })
    candidate_bbls = sorted({item["bbl"] for rows in addresses.values() for item in rows})
    for chunk in _chunks(candidate_bbls):
        placeholders = ",".join("?" for _ in chunk)
        for row in connection.execute(
            f"SELECT bbl,primary_address,units_res,units_total,building_class FROM buildings "
            f"WHERE bbl IN ({placeholders})", tuple(chunk)
        ):
            buildings[row[0]] = {
                "primary_address": row[1], "units_res": row[2],
                "units_total": row[3], "building_class": row[4],
            }
        for bbl, label in connection.execute(
            f"SELECT bbl,unit_label FROM units WHERE bbl IN ({placeholders})", tuple(chunk)
        ):
            bbl_units[bbl] += 1
    for chunk in _chunks(normalized_addresses):
        placeholders = ",".join("?" for _ in chunk)
        for premise_id, bbl, normalized, address, label, normalized_unit in connection.execute(
            f"SELECT p.premise_id,p.bbl,p.normalized,p.address,au.unit_label,au.normalized_unit "
            f"FROM premises p LEFT JOIN addressable_units au ON au.premise_id=p.premise_id "
            f"WHERE p.normalized IN ({placeholders})", tuple(chunk)
        ):
            if label and normalized_unit:
                premises[normalized].append({
                    "premise_id": premise_id, "bbl": bbl, "address": address,
                    "unit_label": label, "normalized_unit": normalized_unit,
                })
    return addresses, buildings, bbl_units, premises


def _listing_rows(connection, properties):
    placeholders = ",".join("?" for _ in properties)
    return connection.execute(
        f"SELECT building_name,address,unit_number,source_id FROM listings "
        f"WHERE source='stuytown' AND building_name IN ({placeholders}) "
        "ORDER BY building_name,address,unit_number,source_id",
        tuple(properties),
    )


def _anchor_bbls(groups, addresses):
    """Learn one BBL anchor per property from unambiguous address matches."""
    anchors = {}
    for property_name, rows in groups.items():
        counts = Counter()
        for row in rows.values():
            candidates = {item["bbl"] for item in addresses[row["normalized_address"]]}
            if len(candidates) == 1:
                counts.update(candidates)
        if counts:
            anchors[property_name] = counts.most_common(1)[0][0]
    return anchors


def _resolve(property_name, candidates, anchor):
    bbls = sorted({item["bbl"] for item in candidates})
    if len(bbls) == 1:
        return bbls[0], "exact_catalog_address"
    if anchor and anchor in bbls:
        return anchor, "property_anchor_disambiguation"
    return None, "ambiguous_catalog_address"


def build_inventory(listings_db, catalog_db, properties=DEFAULT_PROPERTIES):
    listings = sqlite3.connect(listings_db)
    catalog = sqlite3.connect(catalog_db)
    try:
        groups = defaultdict(dict)
        for property_name, address, unit_number, source_id in _listing_rows(listings, properties):
            normalized_address = normalize_address(address)
            group = groups[property_name].setdefault(normalized_address, {
                "property": property_name,
                "address": address,
                "normalized_address": normalized_address,
                "listing_count": 0,
                "listing_unit_labels": set(),
                "listing_source_ids": set(),
            })
            group["listing_count"] += 1
            normalized_unit = normalize_unit(unit_number)
            if normalized_unit:
                group["listing_unit_labels"].add(normalized_unit)
            if source_id:
                group["listing_source_ids"].add(source_id)

        addresses, buildings, bbl_units, premise_units = _catalog_indexes(
            catalog, {normalized for rows in groups.values() for normalized in rows}
        )
        anchors = _anchor_bbls(groups, addresses)
        output_rows = []
        for property_name, rows in sorted(groups.items()):
            for normalized_address, row in sorted(rows.items()):
                candidates = addresses.get(normalized_address, [])
                resolved_bbl, resolution = _resolve(
                    property_name, candidates, anchors.get(property_name)
                )
                candidate_bbls = sorted({item["bbl"] for item in candidates})
                exact_units = sorted({
                    item["normalized_unit"] for item in premise_units.get(normalized_address, [])
                    if not resolved_bbl or item["bbl"] == resolved_bbl
                })
                listing_units = sorted(row["listing_unit_labels"])
                direct_units = sorted(set(listing_units) | set(exact_units))
                building = buildings.get(resolved_bbl) if resolved_bbl else None
                row_out = {
                    "property": property_name,
                    "address": row["address"],
                    "normalized_address": normalized_address,
                    "listing_count": row["listing_count"],
                    "listing_unit_labels": sorted(row["listing_unit_labels"]),
                    "candidate_bbls": candidate_bbls,
                    "resolved_bbl": resolved_bbl,
                    "resolution": resolution,
                    "property_anchor_bbl": anchors.get(property_name),
                    "building": building,
                    "catalog_bbl_unit_count": bbl_units.get(resolved_bbl, 0) if resolved_bbl else 0,
                    "exact_premise_unit_labels": exact_units,
                    "exact_premise_unit_count": len(exact_units),
                    "direct_address_unit_labels": direct_units,
                    "direct_address_unit_count": len(direct_units),
                    "source_status": (
                        "direct_address_evidence_multiple_sources"
                        if listing_units and exact_units else
                        "direct_address_evidence_listing"
                        if listing_units else
                        "direct_address_evidence_premise"
                        if exact_units else "no_exact_address_evidence"
                    ),
                }
                output_rows.append(row_out)
        return {
            "schema_version": 1,
            "source": "stuytown",
            "properties": list(properties),
            "anchors": anchors,
            "address_count": len(output_rows),
            "listing_count": sum(row["listing_count"] for row in output_rows),
            "resolved_address_count": sum(bool(row["resolved_bbl"]) for row in output_rows),
            "ambiguous_address_count": sum(row["resolution"] == "ambiguous_catalog_address" for row in output_rows),
            "addressable_evidence_count": sum(bool(row["exact_premise_unit_labels"]) for row in output_rows),
            "direct_address_evidence_count": sum(bool(row["direct_address_unit_labels"]) for row in output_rows),
            "rows": output_rows,
        }
    finally:
        listings.close()
        catalog.close()


def write_csv(path, rows):
    fields = [
        "property", "address", "normalized_address", "listing_count",
        "listing_unit_labels", "candidate_bbls", "resolved_bbl", "resolution",
        "property_anchor_bbl", "catalog_bbl_unit_count", "exact_premise_unit_labels",
        "exact_premise_unit_count", "direct_address_unit_labels",
        "direct_address_unit_count", "source_status",
    ]
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            rendered = dict(row)
            for field in (
                "listing_unit_labels", "candidate_bbls", "exact_premise_unit_labels",
                "direct_address_unit_labels",
            ):
                rendered[field] = json.dumps(rendered[field], ensure_ascii=True)
            writer.writerow({field: rendered[field] for field in fields})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listings-db", required=True)
    parser.add_argument("--catalog-db", required=True)
    parser.add_argument("--output", required=True, help="JSON inventory path")
    parser.add_argument("--csv", help="Optional flat address inventory path")
    parser.add_argument("--property", dest="properties", action="append", default=[])
    args = parser.parse_args()
    properties = tuple(args.properties) if args.properties else DEFAULT_PROPERTIES
    report = build_inventory(args.listings_db, args.catalog_db, properties)
    output = Path(args.output)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.csv:
        write_csv(args.csv, report["rows"])
    print(json.dumps({key: value for key, value in report.items() if key != "rows"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
