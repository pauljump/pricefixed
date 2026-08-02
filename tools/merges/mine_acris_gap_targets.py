#!/usr/bin/env python3
"""Collect deterministic ACRIS unit evidence for a gap-target CSV.

The output is a review corpus only. It never creates catalog units and never asks
an LLM to interpret an address or document.
"""
import argparse
import csv
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen


API = "https://data.cityofnewyork.us/resource/8h5j-fqxa.json"
ADDRESS_RE = re.compile(r"^\s*(\d+[A-Z]?(?:-\d+[A-Z]?)?)\s+(.+?)\s*$", re.IGNORECASE)


def query_target(target):
    bbl = str(target["bbl"]).zfill(10)
    address = str(target["address"] or "").strip().upper()
    match = ADDRESS_RE.match(address)
    if not match:
        return [{**target, "unit_lot_bbl": "", "unit_label": "", "document_id": "",
                 "observed_at": "", "source_url": "", "status": "unparseable_address"}]
    borough, block = bbl[0], bbl[1:6]
    street_number, street_name = match.groups()
    street_name = street_name.replace("'", "''")
    where = (
        f"borough={borough} AND block={block} AND street_number='{street_number}' "
        f"AND street_name='{street_name}' AND unit IS NOT NULL"
    )
    params = urlencode({
        "$select": "lot,unit,document_id,good_through_date",
        "$where": where,
        "$order": "document_id DESC",
        "$limit": 5000,
    })
    source_url = f"{API}?{params}"
    try:
        with urlopen(source_url, timeout=60) as response:
            rows = json.loads(response.read())
        if isinstance(rows, dict) and rows.get("error"):
            raise RuntimeError(rows.get("message", "ACRIS request failed"))
        output = []
        seen = set()
        for row in rows:
            lot = str(row.get("lot") or "").zfill(4)
            unit = str(row.get("unit") or "").strip()
            key = (lot, unit.upper())
            if not lot or not unit or key in seen:
                continue
            seen.add(key)
            output.append({**target, "unit_lot_bbl": borough + block + lot,
                           "unit_label": unit, "document_id": row.get("document_id", ""),
                           "observed_at": row.get("good_through_date", ""),
                           "source_url": source_url, "status": "unit_row"})
        return output or [{**target, "unit_lot_bbl": "", "unit_label": "", "document_id": "",
                           "observed_at": "", "source_url": source_url, "status": "no_unit_rows"}]
    except Exception as exc:
        return [{**target, "unit_lot_bbl": "", "unit_label": "", "document_id": "",
                 "observed_at": "", "source_url": source_url,
                 "status": f"error:{type(exc).__name__}"}]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.workers <= 0:
        sys.exit("--workers must be positive")
    fields = ("bbl", "borough", "address", "zipcode", "building_class", "capacity_units",
              "named_units", "unresolved_capacity", "unit_lot_bbl", "unit_label",
              "document_id", "observed_at", "source_url", "status")
    with open(args.targets, encoding="utf-8", newline="") as handle:
        targets = list(csv.DictReader(handle))
    output = Path(args.out)
    completed = set()
    if output.exists():
        with output.open(encoding="utf-8", newline="") as handle:
            completed = {row["bbl"] for row in csv.DictReader(handle)}
    targets = [target for target in targets if target["bbl"] not in completed]
    output.parent.mkdir(parents=True, exist_ok=True)
    write_header = not output.exists() or output.stat().st_size == 0
    with output.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if write_header:
            writer.writeheader()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(query_target, target) for target in targets]
            for index, future in enumerate(as_completed(futures), 1):
                writer.writerows(future.result())
                if index % 25 == 0:
                    handle.flush()
                    print(f"completed {index}/{len(targets)} targets", flush=True)
    print(f"wrote evidence for {len(targets)} targets to {output}")


if __name__ == "__main__":
    main()
