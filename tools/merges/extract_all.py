#!/usr/bin/env python3
"""Extract ALL address+unit rows from all 4 archives, raw, no dedup, WITH zip + source record id
for proper provenance and zip-based BBL disambiguation. Reads directly off the external drive."""
import csv
import sqlite3
import sys

OUT = "/Users/mini-home/pricefixed-build/extracted_addresses.csv"

def rows_streeteasy():
    conn = sqlite3.connect("file:/Volumes/Backup Plus/vayo/se_listings.db?mode=ro", uri=True)
    for id_, address, unit in conn.execute(
        "SELECT us.id, b.address, us.unit FROM unit_summary us "
        "JOIN buildings b ON b.slug = us.building_slug "
        "WHERE us.unit IS NOT NULL AND trim(us.unit) <> '' AND b.address IS NOT NULL"
    ):
        yield "streeteasy", address, unit, None, id_

def rows_elliman():
    sys.path.insert(0, "/Users/mini-home/Desktop/unwalled")
    from pricefixed.adapters.elliman import _address_and_unit
    conn = sqlite3.connect("file:/Volumes/Backup Plus/vayo/elliman_mls.db?mode=ro", uri=True)
    for id_, raw_address, raw_unit, zip_ in conn.execute(
        "SELECT core_listing_id, address, unit, zip FROM listings WHERE address IS NOT NULL"
    ):
        address, unit = _address_and_unit({"samlsFullAddress": raw_address, "unitNumber": raw_unit})
        yield "elliman", address, unit, zip_, id_

def rows_corcoran():
    conn = sqlite3.connect("file:/Volumes/Backup Plus/vayo/corcoran.db?mode=ro", uri=True)
    for id_, address, unit, zip_ in conn.execute(
        "SELECT listing_id, address1, address2, zip_code FROM listings"
    ):
        yield "corcoran", address, unit, zip_, id_

def rows_vayo_all_nyc_units():
    conn = sqlite3.connect("file:/Volumes/Backup Plus/vayo/all_nyc_units.db?mode=ro", uri=True)
    for id_, address, unit, zip_ in conn.execute(
        "SELECT unit_id, address, unit_number, zipcode FROM all_nyc_units"
    ):
        yield "vayo_all_nyc_units", address, unit, zip_, id_

def main():
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
