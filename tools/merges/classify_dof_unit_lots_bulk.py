#!/usr/bin/env python3
"""Classify official DOF unit lots from the current bulk assessment roll."""
import argparse
import csv
import gzip
import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DATASET = "8y4t-faws"
API = f"https://data.cityofnewyork.us/resource/{DATASET}.json"
DATASET_URL = f"https://data.cityofnewyork.us/d/{DATASET}"
SELECT = (
    "parid,fintaxclass,curtaxclass,bldg_class,housenum_lo,housenum_hi,"
    "street_name,zip_code,year,period,rectype"
)


def fetch_page(offset, limit, year):
    params = urlencode({
        "$select": SELECT,
        "$where": f"year = '{year}' AND period = '3' AND rectype = '1'",
        "$order": "parid",
        "$limit": limit,
        "$offset": offset,
    })
    url = f"{API}?{params}"
    request = Request(url, headers={
        "Accept-Encoding": "gzip",
        "User-Agent": "pricefixed-public-records/1.0",
    })
    for attempt in range(5):
        try:
            with urlopen(request, timeout=180) as response:
                payload = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    payload = gzip.decompress(payload)
                return json.loads(payload), url
        except HTTPError as exc:
            if exc.code < 500 and exc.code != 429:
                raise
            if attempt == 4:
                raise
        except (URLError, TimeoutError):
            if attempt == 4:
                raise
        time.sleep(2 ** attempt)


def assessment_address(row):
    number = str(row.get("housenum_lo") or "").strip()
    high = str(row.get("housenum_hi") or "").strip()
    if high and high != number:
        number = f"{number}-{high}" if number else high
    return " ".join(part for part in (number, str(row.get("street_name") or "").strip()) if part)


def classification(tax_class):
    value = str(tax_class or "").strip()
    if value in {"1", "1A", "1B", "1C", "1D", "2", "2A", "2B", "2C"}:
        return "residential_tax_class"
    if value == "3":
        return "utility_tax_class"
    if value == "4":
        return "nonresidential_tax_class"
    return "tax_class_not_found"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--year", default="2027")
    parser.add_argument("--batch-size", type=int, default=50000)
    args = parser.parse_args()

    with open(args.input, newline="", encoding="utf-8") as handle:
        input_rows = list(csv.DictReader(handle))
    wanted = {row["unit_lot_bbl"] for row in input_rows}
    assessments = {}
    offset = 0
    while True:
        rows, _url = fetch_page(offset, args.batch_size, args.year)
        for row in rows:
            bbl = str(row.get("parid") or "").strip()
            if bbl in wanted:
                assessments[bbl] = row
        offset += len(rows)
        print(f"assessment rows={offset} matched unit lots={len(assessments)}", flush=True)
        if len(rows) < args.batch_size:
            break

    fields = [
        "unit_lot_bbl", "official_unit_designation", "address", "tax_class",
        "building_class", "assessment_address", "zipcode", "assessment_year",
        "classification", "source_url",
    ]
    counts = {}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for source in input_rows:
            bbl = source["unit_lot_bbl"]
            row = assessments.get(bbl, {})
            tax_class = row.get("fintaxclass") or row.get("curtaxclass") or ""
            status = classification(tax_class)
            counts[status] = counts.get(status, 0) + 1
            writer.writerow({
                "unit_lot_bbl": bbl,
                "official_unit_designation": source.get("official_unit_designation", ""),
                "address": source.get("address", ""),
                "tax_class": tax_class,
                "building_class": row.get("bldg_class", ""),
                "assessment_address": assessment_address(row),
                "zipcode": row.get("zip_code", ""),
                "assessment_year": row.get("year", ""),
                "classification": status,
                "source_url": DATASET_URL,
            })

    summary = {
        "input_unit_lots": len(input_rows),
        "assessment_rows_scanned": offset,
        "matched_unit_lots": len(assessments),
        "assessment_year": args.year,
        "dataset": DATASET,
        "classifications": counts,
        "catalog_writes": 0,
    }
    Path(args.summary).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
