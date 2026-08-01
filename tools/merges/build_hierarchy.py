#!/usr/bin/env python3
"""Resolve the raw extracted addresses into a building(BBL) -> unit hierarchy.

v2: matches the catalog's own `_resolve_bbl` rule exactly (normalized address,
filtered by zipcode when both sides have one) instead of address-only matching.
Remaining multi-candidate cases get one more independent check: does the raw unit
label match exactly one candidate's official condo unit designation
(`official_unit_lots`)? That resolves genuine condo BBL-per-unit fan-out without
ever guessing. Anything still ambiguous or unmatched stays that way, visibly.
"""
import argparse
import csv
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.engine.crosswalk import normalize_address
from pricefixed.engine.dedupe import normalize_unit

CATALOG_DB = None
RAW_CSV = None
OUT_DB = None

_NON_ALNUM = re.compile(r"[^A-Z0-9]")

def norm_designation(s):
    return _NON_ALNUM.sub("", (s or "").upper())

def load_address_index():
    conn = sqlite3.connect(CATALOG_DB)
    index = defaultdict(set)   # normalized address -> set of (bbl, zipcode)
    n = 0
    for normalized, bbl, zipcode in conn.execute("SELECT normalized, bbl, zipcode FROM addresses"):
        index[normalized].add((bbl, zipcode))
        n += 1
    conn.close()
    print(f"loaded {n} official address rows -> {len(index)} distinct normalized addresses", flush=True)
    return index

def load_condo_index():
    conn = sqlite3.connect(CATALOG_DB)
    index = {}   # unit_lot_bbl -> normalized unit_designation
    for bbl, designation in conn.execute(
        "SELECT unit_lot_bbl, unit_designation FROM official_unit_lots WHERE unit_designation IS NOT NULL"
    ):
        index[bbl] = norm_designation(designation)
    conn.close()
    print(f"loaded {len(index)} official condo unit-lot designations", flush=True)
    return index

def zip_filter(candidates, raw_zip):
    """Mirror `_resolve_bbl`: keep a candidate if either side lacks a zip, or they match."""
    if not raw_zip:
        return {bbl for bbl, _ in candidates}
    kept = {bbl for bbl, z in candidates if not z or z == raw_zip}
    return kept if kept else {bbl for bbl, _ in candidates}

def main():
    global CATALOG_DB, RAW_CSV, OUT_DB
    parser = argparse.ArgumentParser(description="Resolve archive address/unit evidence to BBL candidates.")
    parser.add_argument("--catalog-db", required=True, help="catalog SQLite path with addresses and condo lots")
    parser.add_argument("--raw-csv", required=True, help="CSV created by extract_all.py")
    parser.add_argument("--out-db", required=True, help="output hierarchy SQLite path")
    args = parser.parse_args()
    CATALOG_DB, RAW_CSV, OUT_DB = args.catalog_db, args.raw_csv, args.out_db
    addr_index = load_address_index()
    condo_index = load_condo_index()

    out = sqlite3.connect(OUT_DB)
    for t in ("units", "unresolved", "ambiguous"):
        out.execute(f"DROP TABLE IF EXISTS {t}")
    out.execute("""CREATE TABLE units (
        bbl TEXT NOT NULL, unit_normalized TEXT NOT NULL, source TEXT NOT NULL,
        raw_address TEXT, raw_unit TEXT, source_ref TEXT, resolved_via TEXT
    )""")
    out.execute("""CREATE TABLE unresolved (
        source TEXT NOT NULL, raw_address TEXT, raw_unit TEXT, source_ref TEXT, reason TEXT
    )""")
    out.execute("""CREATE TABLE ambiguous (
        source TEXT NOT NULL, raw_address TEXT, raw_unit TEXT, source_ref TEXT, candidate_bbls TEXT
    )""")

    resolved_addr = resolved_condo = unresolved = ambiguous = no_unit = 0
    norm_cache = {}
    BATCH = 20000
    units_buf, unresolved_buf, ambiguous_buf = [], [], []

    with open(RAW_CSV, newline="") as f:
        r = csv.reader(f)
        header = next(r)
        for i, row in enumerate(r, 1):
            source, raw_address, raw_unit, raw_zip, source_ref = (row + [None] * 5)[:5]
            unit_norm = normalize_unit(raw_unit)
            if not unit_norm:
                no_unit += 1
                continue
            na = norm_cache.get(raw_address)
            if na is None:
                na = normalize_address(raw_address) or ""
                norm_cache[raw_address] = na
            if not na:
                unresolved_buf.append((source, raw_address, raw_unit, source_ref, "address did not normalize"))
                unresolved += 1
                continue
            raw_pairs = addr_index.get(na)
            if not raw_pairs:
                unresolved_buf.append((source, raw_address, raw_unit, source_ref, "no official BBL match"))
                unresolved += 1
                continue
            candidates = zip_filter(raw_pairs, raw_zip)
            if len(candidates) == 1:
                units_buf.append((next(iter(candidates)), unit_norm, source, raw_address, raw_unit,
                                   source_ref, "address+zip"))
                resolved_addr += 1
            else:
                # Try to break the tie with the official condo unit designation.
                condo_matches = [bbl for bbl in candidates if condo_index.get(bbl) == unit_norm]
                if len(condo_matches) == 1:
                    units_buf.append((condo_matches[0], unit_norm, source, raw_address, raw_unit,
                                       source_ref, "condo_unit_designation"))
                    resolved_condo += 1
                else:
                    ambiguous_buf.append((source, raw_address, raw_unit, source_ref,
                                           ",".join(sorted(candidates))))
                    ambiguous += 1

            if i % BATCH == 0:
                out.executemany("INSERT INTO units VALUES (?,?,?,?,?,?,?)", units_buf)
                out.executemany("INSERT INTO unresolved VALUES (?,?,?,?,?)", unresolved_buf)
                out.executemany("INSERT INTO ambiguous VALUES (?,?,?,?,?)", ambiguous_buf)
                out.commit()
                units_buf, unresolved_buf, ambiguous_buf = [], [], []
            if i % 500000 == 0:
                print(f"...{i} rows (addr={resolved_addr} condo={resolved_condo} "
                      f"ambiguous={ambiguous} unresolved={unresolved} no_unit={no_unit})", flush=True)

    out.executemany("INSERT INTO units VALUES (?,?,?,?,?,?,?)", units_buf)
    out.executemany("INSERT INTO unresolved VALUES (?,?,?,?,?)", unresolved_buf)
    out.executemany("INSERT INTO ambiguous VALUES (?,?,?,?,?)", ambiguous_buf)
    out.commit()

    resolved = resolved_addr + resolved_condo
    print(f"DONE. resolved={resolved} (address={resolved_addr} condo_tiebreak={resolved_condo}) "
          f"ambiguous={ambiguous} unresolved={unresolved} no_unit_label={no_unit}")
    distinct_bbls = out.execute("SELECT COUNT(DISTINCT bbl) FROM units").fetchone()[0]
    distinct_units = out.execute("SELECT COUNT(DISTINCT bbl || '|' || unit_normalized) FROM units").fetchone()[0]
    print(f"distinct buildings with a resolved unit: {distinct_bbls}")
    print(f"distinct (bbl, unit) pairs: {distinct_units}")

if __name__ == "__main__":
    main()
