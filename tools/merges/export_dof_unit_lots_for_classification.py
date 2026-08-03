#!/usr/bin/env python3
"""Export every official condo unit lot for DOF statement classification."""
import argparse
import csv
import sqlite3
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-db", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--statement-date", default="20251115")
    args = parser.parse_args()
    conn = sqlite3.connect(f"file:{Path(args.catalog_db).resolve()}?mode=ro", uri=True)
    rows = conn.execute(
        "SELECT ol.unit_lot_bbl,ol.unit_designation,COALESCE(MIN(a.address),'') "
        "FROM official_unit_lots ol LEFT JOIN addresses a ON a.bbl=ol.unit_lot_bbl "
        "GROUP BY ol.unit_lot_bbl,ol.unit_designation ORDER BY ol.unit_lot_bbl"
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=(
            "unit_lot_bbl", "official_unit_designation", "address", "source_url"
        ))
        writer.writeheader()
        for bbl, designation, address in rows:
            writer.writerow({
                "unit_lot_bbl": bbl,
                "official_unit_designation": designation or "",
                "address": address,
                "source_url": (
                    "https://a836-edms.nyc.gov/dctm-rest/repositories/dofedmspts/StatementSearch"
                    f"?bbl={bbl}&stmtDate={args.statement_date}&stmtType=SOA"
                ),
            })
            count += 1
    conn.close()
    print(f"wrote {count} official unit lots to {output}")


if __name__ == "__main__":
    main()
