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

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.engine.crosswalk import normalize_address


API = "https://data.cityofnewyork.us/resource/8h5j-fqxa.json"
ADDRESS_RE = re.compile(r"^\s*(\d+[A-Z]?(?:-\d+[A-Z]?)?)\s+(.+?)\s*$", re.IGNORECASE)


def target_bbl(target):
    """Accept the standard gap queue and complex queues with resolved_bbl."""
    return str(target.get("bbl") or target.get("resolved_bbl") or "").strip()


def target_key(target):
    """Checkpoint one exact address, never one shared BBL."""
    bbl = target_bbl(target)
    normalized = normalize_address(target.get("address") or "")
    return f"{bbl}|{normalized or str(target.get('address') or '').strip().upper()}"


def query_target(target):
    raw_bbl = target_bbl(target)
    bbl = raw_bbl.zfill(10)
    address = str(target["address"] or "").strip().upper()
    target = {**target, "bbl": bbl}
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
            completed = {target_key(row) for row in csv.DictReader(handle)}
    targets = [target for target in targets if target_key(target) not in completed]
    output.parent.mkdir(parents=True, exist_ok=True)
    write_header = not output.exists() or output.stat().st_size == 0
    with output.open("a", encoding="utf-8", newline="") as handle:
        input_fields = list(targets[0].keys()) if targets else []
        if output.exists() and output.stat().st_size:
            with output.open(encoding="utf-8", newline="") as existing:
                input_fields = next(csv.reader(existing), input_fields)
        fields = tuple(dict.fromkeys([*input_fields, *fields]))
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
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
