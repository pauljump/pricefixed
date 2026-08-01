#!/usr/bin/env python3
"""Create canonical units directly from DOF's official condo unit-lot registry.

Each row in official_unit_lots is DOF's own tax registration of one individual condo
unit -- a unit_lot_bbl (its own real BBL) plus its unit_designation ("5F", "1A", ...).
This isn't an inference or a tiebreak: it's the taxing authority's direct record that
this exact unit exists and is called this. We already imported this table earlier
today and only used it as an ambiguity tiebreaker; this pass uses it as a first-class
identity source in its own right, for any unit-lot BBL that still has zero named units.
"""
import argparse
import sqlite3
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.engine.dedupe import normalize_unit

DB = None
SOURCE = "dof_condo_unit_lots_direct"

def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())

def _id(*parts):
    return uuid.uuid5(uuid.NAMESPACE_URL, "|".join(str(p) for p in parts)).hex[:20]

def main():
    global DB
    parser = argparse.ArgumentParser(description="Merge direct DOF condo unit-lot identities into a catalog.")
    parser.add_argument("--catalog-db", required=True, help="catalog SQLite path to update")
    DB = parser.parse_args().catalog_db
    c = sqlite3.connect(DB)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    now = _now()

    c.execute(
        "INSERT OR IGNORE INTO sources (source,source_kind,methodology,first_seen,last_seen) VALUES (?,?,?,?,?)",
        (SOURCE, "public_record",
         "DOF condominium unit-lot registry (official_unit_lots, already imported from NYC DOF "
         "condo units dataset). Each row's unit_lot_bbl is DOF's own official BBL for one "
         "individual condo unit; unit_designation is DOF's own name for it. Direct identity, "
         "not an inference: applied only where no unit was ever named on that unit_lot_bbl before.",
         now, now),
    )

    targets = c.execute("""
        WITH named AS (SELECT bbl, COUNT(*) n FROM units GROUP BY bbl)
        SELECT ol.unit_lot_bbl, ol.unit_designation, ol.source_ref, ol.document_id, ol.condo_base_bbl
        FROM official_unit_lots ol LEFT JOIN named n ON n.bbl = ol.unit_lot_bbl
        WHERE ol.unit_designation IS NOT NULL AND n.n IS NULL
    """).fetchall()
    print(f"target unit-lot rows: {len(targets)}", flush=True)

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

    for unit_lot_bbl, designation, source_ref, document_id, condo_base_bbl in targets:
        n += 1
        unit_norm = normalize_unit(designation)
        if not unit_norm:
            continue
        unit_id = _id("unit", unit_lot_bbl, unit_norm)
        unit_buf.append((unit_id, unit_lot_bbl, designation, unit_norm, now, now))

        observation_id = _id("obs", SOURCE, source_ref, "dof_condo_unit_lot_registration")
        obs_buf.append((observation_id, document_id, SOURCE, str(source_ref), now,
                         "dof_condo_unit_lot_registration", None, designation, "source_document"))

        match_buf.append((observation_id, "building", unit_lot_bbl, "resolved", 1.0, "dof_unit_lot_bbl",
                           f"DOF issued this BBL directly as one condo unit within base building {condo_base_bbl}", now))
        match_buf.append((observation_id, "unit", unit_id, "resolved", 1.0, "dof_unit_designation",
                           "DOF's own designation for this unit-lot BBL", now))

        if n % BATCH == 0:
            flush()
        if n % 50000 == 0:
            print(f"...{n}", flush=True)

    flush()
    print(f"DONE. created units for {n} unit-lot rows")
    print("total units now:", c.execute("SELECT COUNT(*) FROM units").fetchone()[0])

if __name__ == "__main__":
    main()
