#!/usr/bin/env python3
"""Export buildings where a unit-label document could materially improve coverage."""
import argparse
import csv
import sqlite3
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Export ranked unit-document targets.")
    parser.add_argument("--catalog-db", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--min-capacity", type=int, default=2)
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()
    database = Path(args.catalog_db)
    output = Path(args.out)
    if not database.is_file():
        sys.exit(f"catalog database not found: {database}")
    if args.min_capacity <= 0 or args.limit <= 0:
        sys.exit("--min-capacity and --limit must be positive")

    connection = sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True)
    try:
        buildings = connection.execute(
            "SELECT bbl,borough,primary_address,zipcode,building_class,units_res "
            "FROM buildings WHERE units_res >= ? ORDER BY units_res DESC,bbl LIMIT ?",
            # Oversample modestly so buildings with complete confirmed coverage
            # do not consume the whole queue, without scanning the whole city.
            (args.min_capacity, max(args.limit * 2, args.limit)),
        ).fetchall()
        bbls = [building[0] for building in buildings]
        placeholders = ",".join("?" for _ in bbls)
        counts = {
            bbl: (confirmed or 0, candidates or 0)
            for bbl, confirmed, candidates in connection.execute(
                "SELECT u.bbl, COUNT(DISTINCT CASE WHEN em.status='resolved' THEN u.unit_id END), "
                "COUNT(DISTINCT CASE WHEN em.status='candidate' THEN u.unit_id END) "
                "FROM units u INDEXED BY idx_units_bbl JOIN entity_matches em INDEXED BY idx_matches_entity "
                "ON em.entity_type='unit' AND em.entity_id=u.unit_id "
                f"WHERE u.bbl IN ({placeholders}) GROUP BY u.bbl",
                bbls,
            )
        }
        rows = []
        for building in buildings:
            confirmed, candidates = counts.get(building[0], (0, 0))
            remaining = building[5] - confirmed
            if remaining > 0:
                rows.append((*building, confirmed, candidates, remaining))
        rows.sort(key=lambda row: (-row[-1], -row[5], row[0]))
        rows = rows[:args.limit]
    finally:
        connection.close()

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("bbl", "borough", "address", "zipcode", "building_class",
                         "capacity_units", "confirmed_units", "candidate_units",
                         "remaining_capacity"))
        writer.writerows(rows)
    print(f"wrote {len(rows)} targets to {output}")


if __name__ == "__main__":
    main()
