#!/usr/bin/env python3
"""Retry unresolved DOF unit addresses with the current deterministic parser."""
import argparse
import csv
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from mine_dof_unit_addresses import fetch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--statement-date", default="20251115")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    output = Path(args.output)
    completed = set()
    if output.exists():
        with output.open(encoding="utf-8", newline="") as handle:
            completed = {row["unit_lot_bbl"] for row in csv.DictReader(handle)}
    with open(args.input, encoding="utf-8", newline="") as handle:
        rows = [
            (row["unit_lot_bbl"], row.get("official_unit_designation") or row.get("unit_designation") or "")
            for row in csv.DictReader(handle)
            if row["unit_lot_bbl"] not in completed
        ]
    fields = ("unit_lot_bbl", "unit_designation", "address", "source_url", "statement_date", "status")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if output.stat().st_size == 0:
            writer.writeheader()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(fetch, row, args.statement_date) for row in rows]
            for index, future in enumerate(as_completed(futures), 1):
                writer.writerow(future.result())
                if index % 100 == 0:
                    handle.flush()
                    print(f"completed {index}/{len(rows)}", flush=True)
                time.sleep(0.02)
    print(f"wrote {len(rows)} retry results to {output}")


if __name__ == "__main__":
    main()
