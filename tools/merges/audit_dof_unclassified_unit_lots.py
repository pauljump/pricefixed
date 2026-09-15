#!/usr/bin/env python3
"""Audit unresolved DOF unit-lot classifications against historical rolls.

The current DOF assessment roll can omit individual condo tax lots that still
exist in the official condominium-unit registry. This tool checks those exact
BBLs against bounded historical assessment years. It produces evidence for
review only: it never classifies a lot in place and never writes the catalog.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DATASET = "kevu-8hby"
API = f"https://data.cityofnewyork.us/resource/{DATASET}.json"
SELECT = "bble,txcl,bldgcl,year4,hnum_lo,str_name,zip"
RESIDENTIAL_TAX_CLASSES = {"1", "1A", "1B", "1C", "1D", "2", "2A", "2B", "2C"}


def query(bbls, year):
    """Return historical rows and the exact public query URL for a BBL chunk."""
    values = ",".join("'%s'" % str(bbl).replace("'", "''") for bbl in bbls)
    where = f"year4='{str(year).replace(chr(39), chr(39) * 2)}' AND bble in ({values})"
    params = urlencode({
        "$select": SELECT,
        "$where": where,
        "$order": "bble",
        "$limit": 5000,
    })
    url = f"{API}?{params}"
    request = Request(url, headers={"User-Agent": "pricefixed-public-records/1.0"})
    with urlopen(request, timeout=180) as response:
        payload = json.loads(response.read())
    if isinstance(payload, dict) and payload.get("error"):
        raise RuntimeError(payload.get("message", "DOF historical assessment query failed"))
    return payload, url


def _targets(path, only_unclassified=True):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if only_unclassified:
        rows = [row for row in rows if row.get("classification") == "tax_class_not_found"]
    unique = {}
    for row in rows:
        bbl = str(row.get("unit_lot_bbl") or "").strip()
        if bbl:
            unique.setdefault(bbl, row)
    return unique


def audit(targets, years, chunk_size=200, pause=0.1):
    """Collect historical evidence without upgrading any target's status."""
    bbls = list(targets)
    output = []
    for year in years:
        for start in range(0, len(bbls), chunk_size):
            chunk = bbls[start:start + chunk_size]
            rows, source_url = query(chunk, year)
            by_bbl = {}
            for row in rows:
                by_bbl.setdefault(str(row.get("bble") or ""), []).append(row)
            for bbl in chunk:
                matches = by_bbl.get(bbl) or []
                if not matches:
                    output.append({
                        **targets[bbl],
                        "historical_dataset": DATASET,
                        "historical_year": str(year),
                        "historical_tax_class": "",
                        "historical_building_class": "",
                        "historical_address": "",
                        "historical_zip": "",
                        "source_url": source_url,
                        "status": "no_historical_match",
                        "raw_row": "",
                    })
                    continue
                for row in matches:
                    tax_class = str(row.get("txcl") or "").strip().upper()
                    output.append({
                        **targets[bbl],
                        "historical_dataset": DATASET,
                        "historical_year": str(row.get("year4") or year),
                        "historical_tax_class": tax_class,
                        "historical_building_class": str(row.get("bldgcl") or ""),
                        "historical_address": " ".join(
                            str(value).strip() for value in (row.get("hnum_lo"), row.get("str_name")) if value
                        ),
                        "historical_zip": str(row.get("zip") or ""),
                        "source_url": source_url,
                        "status": (
                            "historical_residential_tax_class"
                            if tax_class in RESIDENTIAL_TAX_CLASSES
                            else "historical_nonresidential_or_other_tax_class"
                        ),
                        "raw_row": json.dumps(row, sort_keys=True, separators=(",", ":")),
                    })
            if pause:
                time.sleep(pause)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="DOF classification CSV")
    parser.add_argument("--out", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--years", default="2015,2016,2017")
    parser.add_argument("--chunk-size", type=int, default=200)
    parser.add_argument("--include-classified", action="store_true")
    args = parser.parse_args()
    if args.chunk_size <= 0:
        parser.error("--chunk-size must be positive")
    years = [year.strip() for year in args.years.split(",") if year.strip()]
    if not years:
        parser.error("--years must contain at least one year")
    targets = _targets(args.input, only_unclassified=not args.include_classified)
    rows = audit(targets, years, chunk_size=args.chunk_size)
    target_fields = list(next(iter(targets.values())).keys()) if targets else []
    fields = list(dict.fromkeys([
        *target_fields,
        "historical_dataset", "historical_year", "historical_tax_class",
        "historical_building_class", "historical_address", "historical_zip",
        "source_url", "status", "raw_row",
    ]))
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "input_targets": len(targets),
        "years": years,
        "evidence_rows": len(rows),
        "target_statuses": dict(sorted(Counter(row["status"] for row in rows).items())),
        "historical_residential_candidates": sum(
            row["status"] == "historical_residential_tax_class" for row in rows
        ),
        "catalog_writes": 0,
        "policy": "historical evidence is review-only and does not classify or create catalog units",
    }
    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
