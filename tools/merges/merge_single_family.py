#!/usr/bin/env python3
"""Create one canonical unit for every BBL where PLUTO says units_res=1 AND no
apartment has ever been named there. For a one-family house the building IS the
dwelling -- there is no subdivision to discover, so naming it invents nothing.
This is corroboration between two already-imported official sources (PLUTO count +
official PAD-derived address), not a guess, and it's tagged with its own evidence
grade so it's never confused with a directly-observed apartment label.
"""
import sqlite3
import time
import uuid

DB = "/Users/mini-home/pricefixed-build/catalog.db"
SOURCE = "pluto_single_family_dwelling"
NORMALIZED_UNIT = "WHOLEBLDG"

def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())

def _id(*parts):
    return uuid.uuid5(uuid.NAMESPACE_URL, "|".join(str(p) for p in parts)).hex[:20]

def main():
    c = sqlite3.connect(DB)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    now = _now()

    c.execute(
        "INSERT OR IGNORE INTO sources (source,source_kind,methodology,first_seen,last_seen) VALUES (?,?,?,?,?)",
        (SOURCE, "derived_inference",
         "PLUTO units_res=1 (one residential unit on the tax lot) plus an already-resolved "
         "official PAD address on the same BBL: two independent official sources agreeing "
         "the entire building is one dwelling. Never applied when units_res != 1 or when any "
         "named apartment already exists on the BBL.", now, now),
    )

    targets = c.execute("""
        WITH named AS (SELECT bbl, COUNT(*) n FROM units GROUP BY bbl)
        SELECT b.bbl, b.primary_address FROM buildings b LEFT JOIN named n ON n.bbl = b.bbl
        WHERE b.units_res = 1 AND n.n IS NULL
          AND b.primary_address IS NOT NULL AND trim(b.primary_address) <> ''
    """).fetchall()
    print(f"target BBLs: {len(targets)}", flush=True)

    unit_buf, obs_buf, match_buf = [], [], []
    BATCH = 20000
    n = 0

    def flush():
        nonlocal unit_buf, obs_buf, match_buf
        c.executemany(
            "INSERT INTO units (unit_id,bbl,unit_label,normalized_unit,first_seen,last_seen) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(bbl,normalized_unit) DO NOTHING", unit_buf)
        c.executemany(
            "INSERT INTO observations (observation_id,document_id,source,source_ref,observed_at,observation_kind,"
            "address,unit_label,evidence_grade) VALUES (?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(source,source_ref,observed_at,observation_kind) DO NOTHING", obs_buf)
        c.executemany(
            "INSERT INTO entity_matches (observation_id,entity_type,entity_id,status,confidence,method,rationale,matched_at) "
            "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(observation_id,entity_type) DO NOTHING", match_buf)
        c.commit()
        unit_buf, obs_buf, match_buf = [], [], []

    for bbl, address in targets:
        n += 1
        unit_id = _id("unit", bbl, NORMALIZED_UNIT)
        unit_buf.append((unit_id, bbl, "(whole building)", NORMALIZED_UNIT, now, now))

        observation_id = _id("obs", SOURCE, bbl, "single_family_inference")
        obs_buf.append((observation_id, None, SOURCE, bbl, now, "single_family_inference",
                         address, "(whole building)", "derived_inference"))

        match_buf.append((observation_id, "building", bbl, "resolved", 1.0, "pluto_units_res_and_pad",
                           "BBL already resolved from imported PLUTO/PAD records", now))
        match_buf.append((observation_id, "unit", unit_id, "resolved", 1.0, "pluto_units_res_equals_one",
                           "PLUTO units_res=1 and no other apartment ever named on this BBL: "
                           "the building itself is the single dwelling unit", now))

        if n % BATCH == 0:
            flush()
        if n % 50000 == 0:
            print(f"...{n}", flush=True)

    flush()
    print(f"DONE. created {n} single-family units")
    print("total units now:", c.execute("SELECT COUNT(*) FROM units").fetchone()[0])

if __name__ == "__main__":
    main()
