#!/usr/bin/env python3
"""Validate DOF unit-address evidence against official condo unit lots."""
import argparse
import csv
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path


def normalize(value):
    return re.sub(r"\s+", " ", str(value or "").strip().upper())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-db", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--retry", help="optional retry CSV; address_found rows replace base results")
    parser.add_argument("--accepted", required=True)
    parser.add_argument("--rejected", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()

    conn = sqlite3.connect(f"file:{Path(args.catalog_db).resolve()}?mode=ro", uri=True)
    try:
        official = {
            row[0]: row[1]
            for row in conn.execute("SELECT unit_lot_bbl,unit_designation FROM official_unit_lots")
        }
    finally:
        conn.close()

    input_rows = {}
    with open(args.input, encoding="utf-8", newline="") as handle:
        input_rows = {row["unit_lot_bbl"]: row for row in csv.DictReader(handle)}
    if args.retry:
        with open(args.retry, encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if row["status"] == "address_found":
                    input_rows[row["unit_lot_bbl"]] = row

    accepted = []
    rejected = []
    for row in input_rows.values():
        bbl = normalize(row["unit_lot_bbl"])
        address = normalize(row["address"])
        reasons = []
        if row["status"] != "address_found":
            reasons.append(row["status"])
        if bbl not in official:
            reasons.append("not_in_official_unit_lots")
        if not address:
            reasons.append("empty_address")
        result = {**row, "unit_lot_bbl": bbl, "address": address,
                  "official_unit_designation": official.get(bbl, ""),
                  "validation_status": "accepted" if not reasons else "rejected",
                  "validation_reason": ";".join(reasons)}
        (accepted if not reasons else rejected).append(result)

    fields = list(accepted[0] if accepted else rejected[0])
    for path, rows in ((Path(args.accepted), accepted), (Path(args.rejected), rejected)):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    summary = {
        "input_rows": len(accepted) + len(rejected),
        "accepted_rows": len(accepted),
        "rejected_rows": len(rejected),
        "rejection_reasons": dict(sorted(Counter(
            reason for row in rejected for reason in row["validation_reason"].split(";") if reason
        ).items())),
        "catalog_unit_lots": len(official),
        "catalog_writes": 0,
    }
    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"accepted {len(accepted)} rows; rejected {len(rejected)} rows")
    print(f"wrote summary to {summary_path}")


if __name__ == "__main__":
    main()
