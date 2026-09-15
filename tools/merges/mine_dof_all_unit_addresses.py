#!/usr/bin/env python3
"""Mine public DOF statements for addresses across all official condo units."""
import argparse
import csv
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from mine_dof_unit_addresses import fetch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-db", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--statement-date", default="20251115")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.workers <= 0:
        sys.exit("--workers must be positive")

    output = Path(args.out)
    completed = set()
    if output.exists():
        with output.open(encoding="utf-8", newline="") as handle:
            completed = {row["unit_lot_bbl"] for row in csv.DictReader(handle)}
    conn = sqlite3.connect(f"file:{Path(args.catalog_db).resolve()}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT unit_lot_bbl,unit_designation FROM official_unit_lots "
            "WHERE unit_lot_bbl NOT IN (SELECT bbl FROM addresses) ORDER BY unit_lot_bbl"
        ).fetchall()
    finally:
        conn.close()
    rows = [row for row in rows if row[0] not in completed]
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = ("unit_lot_bbl", "unit_designation", "address", "source_url", "statement_date", "status")
    with output.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if not completed and output.stat().st_size == 0:
            writer.writeheader()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            completed_now = 0
            for start in range(0, len(rows), 500):
                batch = rows[start:start + 500]
                futures = [pool.submit(fetch, row, args.statement_date) for row in batch]
                for future in as_completed(futures):
                    writer.writerow(future.result())
                    completed_now += 1
                    if completed_now % 100 == 0:
                        handle.flush()
                        print(f"completed {completed_now}/{len(rows)}", flush=True)
                    time.sleep(0.02)
    print(f"wrote {len(rows)} new results to {output}")


if __name__ == "__main__":
    main()
