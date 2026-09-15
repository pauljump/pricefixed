#!/usr/bin/env python3
"""Export a ranked queue of buildings whose dwelling capacity is unnamed."""
import argparse
import csv
import sqlite3
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Export high-value unresolved housing-capacity targets.")
    parser.add_argument("--catalog-db", required=True, help="catalog SQLite database")
    parser.add_argument("--out", required=True, help="CSV output path")
    parser.add_argument("--min-capacity", type=int, default=20, help="minimum PLUTO residential capacity")
    parser.add_argument("--limit", type=int, default=500, help="maximum targets to export")
    args = parser.parse_args()

    database = Path(args.catalog_db)
    output = Path(args.out)
    if not database.is_file():
        sys.exit(f"catalog database not found: {database}")
    if args.min_capacity <= 0 or args.limit <= 0:
        sys.exit("--min-capacity and --limit must be positive")

    connection = sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "WITH named AS ("
            " SELECT bbl, COUNT(*) AS named_units FROM units GROUP BY bbl"
            ") SELECT b.bbl,b.borough,b.primary_address,b.zipcode,b.building_class,b.units_res,"
            " COALESCE(named.named_units,0) AS named_units,"
            " b.units_res-COALESCE(named.named_units,0) AS unresolved_capacity"
            " FROM buildings b LEFT JOIN named ON named.bbl=b.bbl"
            " WHERE b.units_res >= ? AND b.units_res-COALESCE(named.named_units,0) > 0"
            " ORDER BY unresolved_capacity DESC,b.units_res DESC,b.bbl LIMIT ?",
            (args.min_capacity, args.limit),
        ).fetchall()
    finally:
        connection.close()

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("bbl", "borough", "address", "zipcode", "building_class",
                         "capacity_units", "named_units", "unresolved_capacity"))
        writer.writerows(rows)
    print(f"wrote {len(rows)} targets to {output}")


if __name__ == "__main__":
    main()
