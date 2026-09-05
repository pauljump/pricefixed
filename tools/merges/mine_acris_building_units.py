#!/usr/bin/env python3
"""Export deduplicated ACRIS unit-legals for one exact building address."""
import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen


DATASET = "8h5j-fqxa"
API = f"https://data.cityofnewyork.us/resource/{DATASET}.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--borough", required=True, help="ACRIS numeric borough code")
    parser.add_argument("--block", required=True)
    parser.add_argument("--street-number", required=True)
    parser.add_argument("--street-name", required=True)
    parser.add_argument("--address", required=True, help="canonical display address")
    parser.add_argument("--catalog-db", help="optional catalog for official unit-lot flag")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    where = (
        f"borough={args.borough} AND block={args.block} "
        f"AND street_number='{args.street_number}' "
        f"AND street_name='{args.street_name.upper().replace(chr(39), chr(39) + chr(39))}' "
        "AND unit IS NOT NULL"
    )
    params = urlencode({
        "$select": "lot,unit,document_id,good_through_date",
        "$where": where,
        "$order": "document_id DESC",
        "$limit": 5000,
    })
    source_url = f"{API}?{params}"
    with urlopen(source_url, timeout=60) as response:
        rows = json.loads(response.read())
    if isinstance(rows, dict) and rows.get("error"):
        sys.exit(rows.get("message", "ACRIS request failed"))

    official = set()
    if args.catalog_db:
        conn = sqlite3.connect(f"file:{Path(args.catalog_db).resolve()}?mode=ro", uri=True)
        try:
            official = {
                row[0] for row in conn.execute(
                    "SELECT unit_lot_bbl FROM official_unit_lots"
                )
            }
        finally:
            conn.close()

    unique = {}
    for row in rows:
        lot = str(row.get("lot") or "").zfill(4)
        unit = str(row.get("unit") or "").strip()
        if not lot or not unit:
            continue
        unit_lot_bbl = f"{args.borough}{args.block.zfill(5)}{lot}"
        unique.setdefault((unit_lot_bbl, unit.upper()), {
            "unit_lot_bbl": unit_lot_bbl,
            "unit_label": unit,
            "address": args.address,
            "document_id": row.get("document_id", ""),
            "observed_at": row.get("good_through_date", ""),
            "source_url": source_url,
            "official_unit_lot": "yes" if unit_lot_bbl in official else "no",
        })

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = ("unit_lot_bbl", "unit_label", "address", "document_id", "observed_at", "source_url", "official_unit_lot")
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sorted(unique.values(), key=lambda item: (item["unit_label"], item["unit_lot_bbl"])))
    print(f"wrote {len(unique)} distinct unit labels to {output}")


if __name__ == "__main__":
    main()
