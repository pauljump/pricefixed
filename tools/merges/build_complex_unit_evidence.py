#!/usr/bin/env python3
"""Build a deterministic unit-evidence matrix from a complex inventory and source packets."""
import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.engine.crosswalk import normalize_address
from pricefixed.engine.dedupe import normalize_unit
from pricefixed.engine.identifiers import normalize_bbl
from tools.merges.audit_building_unit_sources import (
    _iter_packets,
    _parser_for,
)


def _normalized_labels(labels):
    return sorted({normalized for label in labels for normalized in [normalize_unit(label)] if normalized})


def _catalog_labels(connection, bbls):
    labels = defaultdict(set)
    for bbl in bbls:
        for label, in connection.execute(
            "SELECT unit_label FROM units WHERE bbl=?", (bbl,)
        ):
            normalized = normalize_unit(label)
            if normalized:
                labels[bbl].add(normalized)
    return labels


def build_evidence(inventory_path, catalog_db, packet_paths):
    inventory = json.loads(Path(inventory_path).read_text(encoding="utf-8"))
    rows = inventory.get("rows") or []
    by_address = {}
    property_bbls = {}
    property_labels = defaultdict(set)
    for row in rows:
        normalized = row["normalized_address"]
        by_address[(row["property"], normalized)] = {
            **row,
            "packet_exact_unit_labels": set(),
            "packet_exact_hit_count": 0,
        }
        bbl = row.get("resolved_bbl")
        if bbl:
            property_bbls.setdefault(row["property"], set()).add(bbl)

    packet_stats = defaultdict(lambda: {"exact_hits": 0, "shared_hits": 0})
    for packet_path in packet_paths:
        for line_number, packet in _iter_packets(packet_path):
            packet_address = normalize_address(packet.get("target_address") or "")
            packet_bbl = normalize_bbl(packet.get("bbl")) or ""
            parsed = _normalized_labels(_parser_for(packet)(packet.get("text") or ""))
            if not parsed:
                continue
            exact_matches = [
                key for key in by_address
                if key[1] == packet_address and packet_address
            ]
            if exact_matches:
                for key in exact_matches:
                    row = by_address[key]
                    row["packet_exact_unit_labels"].update(parsed)
                    row["packet_exact_hit_count"] += 1
                    packet_stats[key[0]]["exact_hits"] += 1
                continue
            for property_name, bbls in property_bbls.items():
                if packet_bbl in bbls:
                    property_labels[property_name].update(parsed)
                    packet_stats[property_name]["shared_hits"] += 1

    catalog = sqlite3.connect(catalog_db)
    try:
        catalog_labels = _catalog_labels(
            catalog, {bbl for bbls in property_bbls.values() for bbl in bbls}
        )
    finally:
        catalog.close()

    rendered_rows = []
    for key in sorted(by_address):
        row = by_address[key]
        listing_labels = set(_normalized_labels(row.get("listing_unit_labels") or []))
        premise_labels = set(_normalized_labels(row.get("exact_premise_unit_labels") or []))
        packet_labels = row.pop("packet_exact_unit_labels")
        direct_labels = listing_labels | premise_labels | packet_labels
        row["listing_unit_labels"] = sorted(listing_labels)
        row["exact_premise_unit_labels"] = sorted(premise_labels)
        row["packet_exact_unit_labels"] = sorted(packet_labels)
        row["packet_exact_unit_count"] = len(packet_labels)
        row["direct_address_unit_labels"] = sorted(direct_labels)
        row["direct_address_unit_count"] = len(direct_labels)
        rendered_rows.append(row)

    rendered_properties = []
    for property_name in sorted(property_bbls):
        bbls = sorted(property_bbls[property_name])
        property_packet_exact_labels = {
            label for row in rendered_rows if row["property"] == property_name
            for label in row["packet_exact_unit_labels"]
        }
        labels = set(property_labels[property_name])
        labels.update(property_packet_exact_labels)
        for bbl in bbls:
            labels.update(catalog_labels[bbl])
        property_rows = [row for row in rendered_rows if row["property"] == property_name]
        rendered_properties.append({
            "property": property_name,
            "bbls": bbls,
            "address_count": len(property_rows),
            "catalog_bbl_unit_labels": sorted({
                label for bbl in bbls for label in catalog_labels[bbl]
            }),
            "packet_exact_address_unit_labels": sorted(property_packet_exact_labels),
            "packet_shared_bbl_unit_labels": sorted(property_labels[property_name]),
            "bbl_source_unit_labels": sorted(labels),
            "packet_stats": dict(packet_stats[property_name]),
        })

    return {
        "schema_version": 1,
        "inventory": str(inventory_path),
        "packet_sources": [str(path) for path in packet_paths],
        "address_count": len(rendered_rows),
        "direct_evidence_address_count": sum(
            bool(row["direct_address_unit_labels"]) for row in rendered_rows
        ),
        "properties": rendered_properties,
        "rows": rendered_rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--catalog-db", required=True)
    parser.add_argument("--packets", action="append", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = build_evidence(args.inventory, args.catalog_db, args.packets)
    Path(args.output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in {"rows", "properties"}}, indent=2))


if __name__ == "__main__":
    main()
