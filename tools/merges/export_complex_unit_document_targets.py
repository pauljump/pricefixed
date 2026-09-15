#!/usr/bin/env python3
"""Export complex addresses that still need a direct unit-bearing document."""
import argparse
import csv
import json
from pathlib import Path


FIELDS = (
    "property", "address", "normalized_address", "resolved_bbl", "listing_count",
    "direct_address_unit_count", "catalog_bbl_unit_count", "packet_exact_hit_count",
    "inventory_origin", "next_source",
)


def export_targets(evidence_path, output_path, include_observed=False):
    report = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
    rows = []
    for row in report.get("rows") or []:
        if not include_observed and row.get("direct_address_unit_count", 0):
            continue
        rows.append({
            "property": row.get("property", ""),
            "address": row.get("address", ""),
            "normalized_address": row.get("normalized_address", ""),
            "resolved_bbl": row.get("resolved_bbl", ""),
            "listing_count": row.get("listing_count", 0),
            "direct_address_unit_count": row.get("direct_address_unit_count", 0),
            "catalog_bbl_unit_count": row.get("catalog_bbl_unit_count", 0),
            "packet_exact_hit_count": row.get("packet_exact_hit_count", 0),
            "inventory_origin": row.get("inventory_origin", ""),
            "next_source": "DOB occupancy document, Schedule A, I-card, or filed plan",
        })
    rows.sort(key=lambda row: (row["property"], row["address"]))
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--include-observed", action="store_true",
        help="Include addresses that already have direct unit evidence",
    )
    args = parser.parse_args()
    rows = export_targets(args.evidence, args.out, args.include_observed)
    print(f"wrote {len(rows)} targets to {args.out}")


if __name__ == "__main__":
    main()
