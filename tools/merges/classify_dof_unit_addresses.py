#!/usr/bin/env python3
"""Classify accepted DOF unit addresses by tax class from public statements."""
import argparse
import csv
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen


TAX_CLASS_RE = re.compile(r"Tax class:\s*([1-4])\s*-\s*([^\r\n]+)", re.IGNORECASE)


def fetch(row):
    try:
        request = Request(row["source_url"], headers={"User-Agent": "pricefixed-public-records/1.0"})
        with urlopen(request, timeout=30) as response:
            pdf = response.read()
        text = subprocess.run(
            ["pdftotext", "-", "-"], input=pdf, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, check=True,
        ).stdout.decode("utf-8", errors="replace")
        match = TAX_CLASS_RE.search(text)
        return {
            "unit_lot_bbl": row["unit_lot_bbl"],
            "unit_designation": row["official_unit_designation"],
            "address": row["address"],
            "tax_class": match.group(1) if match else "",
            "tax_class_description": match.group(2).strip() if match else "",
            "source_url": row["source_url"],
            "status": "classified" if match else "tax_class_not_found",
        }
    except Exception as exc:
        return {
            "unit_lot_bbl": row["unit_lot_bbl"],
            "unit_designation": row["official_unit_designation"],
            "address": row["address"],
            "tax_class": "",
            "tax_class_description": "",
            "source_url": row["source_url"],
            "status": f"error:{type(exc).__name__}",
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    output = Path(args.output)
    completed = set()
    if output.exists():
        with output.open(encoding="utf-8", newline="") as handle:
            completed = {row["unit_lot_bbl"] for row in csv.DictReader(handle)}
    with open(args.input, encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["unit_lot_bbl"] not in completed]
    fields = ("unit_lot_bbl", "unit_designation", "address", "tax_class",
              "tax_class_description", "source_url", "status")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if output.stat().st_size == 0:
            writer.writeheader()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            completed_now = 0
            for start in range(0, len(rows), 500):
                futures = [pool.submit(fetch, row) for row in rows[start:start + 500]]
                for future in as_completed(futures):
                    writer.writerow(future.result())
                    completed_now += 1
                    if completed_now % 100 == 0:
                        handle.flush()
                        print(f"completed {completed_now}/{len(rows)}", flush=True)
                    time.sleep(0.02)
    print(f"wrote {len(rows)} new classifications to {output}")


if __name__ == "__main__":
    main()
