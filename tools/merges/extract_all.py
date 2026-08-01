#!/usr/bin/env python3
"""Extract ALL address+unit rows from all 4 archives, raw, no dedup, WITH zip + source record id
for proper provenance and zip-based BBL disambiguation. Reads directly off the external drive."""
import argparse
import csv
import sqlite3
import sys

OUT = None
STREETEASY_DB = None
ELLIMAN_DB = None
CORCORAN_DB = None
VAYO_DB = None

def rows_streeteasy():
    conn = sqlite3.connect(f"file:{STREETEASY_DB}?mode=ro", uri=True)
    for id_, address, unit in conn.execute(
        "SELECT us.id, b.address, us.unit FROM unit_summary us "
        "JOIN buildings b ON b.slug = us.building_slug "
        "WHERE us.unit IS NOT NULL AND trim(us.unit) <> '' AND b.address IS NOT NULL"
    ):
        yield "streeteasy", address, unit, None, id_

def rows_elliman():
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pricefixed.adapters.elliman import _address_and_unit
    conn = sqlite3.connect(f"file:{ELLIMAN_DB}?mode=ro", uri=True)
    for id_, raw_address, raw_unit, zip_ in conn.execute(
        "SELECT core_listing_id, address, unit, zip FROM listings WHERE address IS NOT NULL"
    ):
        address, unit = _address_and_unit({"samlsFullAddress": raw_address, "unitNumber": raw_unit})
        yield "elliman", address, unit, zip_, id_

def rows_corcoran():
    conn = sqlite3.connect(f"file:{CORCORAN_DB}?mode=ro", uri=True)
    for id_, address, unit, zip_ in conn.execute(
        "SELECT listing_id, address1, address2, zip_code FROM listings"
    ):
        yield "corcoran", address, unit, zip_, id_

def rows_vayo_all_nyc_units():
    conn = sqlite3.connect(f"file:{VAYO_DB}?mode=ro", uri=True)
    for id_, address, unit, zip_ in conn.execute(
        "SELECT unit_id, address, unit_number, zipcode FROM all_nyc_units"
    ):
        yield "vayo_all_nyc_units", address, unit, zip_, id_

def main():
    global OUT, STREETEASY_DB, ELLIMAN_DB, CORCORAN_DB, VAYO_DB
    parser = argparse.ArgumentParser(description="Extract raw address/unit evidence from archive databases.")
    parser.add_argument("--out", required=True, help="output CSV path")
    parser.add_argument("--streeteasy-db", required=True, help="archived StreetEasy SQLite path")
    parser.add_argument("--elliman-db", required=True, help="archived Elliman SQLite path")
    parser.add_argument("--corcoran-db", required=True, help="archived Corcoran SQLite path")
    parser.add_argument("--vayo-db", required=True, help="archived all_nyc_units SQLite path")
    args = parser.parse_args()
    OUT, STREETEASY_DB, ELLIMAN_DB, CORCORAN_DB, VAYO_DB = (
        args.out, args.streeteasy_db, args.elliman_db, args.corcoran_db, args.vayo_db
    )
    total = 0
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["source", "address", "unit", "zip", "source_ref"])
        for fn in (rows_streeteasy, rows_elliman, rows_corcoran, rows_vayo_all_nyc_units):
            n = 0
            for row in fn():
                w.writerow(row)
                n += 1
                if n % 500000 == 0:
                    print(f"{fn.__name__}: ...{n}", flush=True)
            total += n
            print(f"{fn.__name__}: {n} rows total", flush=True)
    print(f"TOTAL: {total} rows -> {OUT}")

if __name__ == "__main__":
    main()
