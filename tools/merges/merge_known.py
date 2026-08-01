#!/usr/bin/env python3
"""Merge the KNOWN (evidence-backed, non-synthetic) resolved units into catalog.db,
tagged with their real source. Excludes PLUTO_INFERRED rows from vayo_all_nyc_units
(synthetic placeholder unit numbers, not observed evidence). Identity only -- no price.
"""
import argparse
import sqlite3
import sys
import time
import uuid

H_DB = None
C_DB = None
VAYO_DB = None

def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())

def _id(*parts):
    return uuid.uuid5(uuid.NAMESPACE_URL, "|".join(str(p) for p in parts)).hex[:20]

def classify_vayo(h):
    """unit_id -> real source label, or None if PLUTO_INFERRED-only (synthetic)."""
    refs = [r[0] for r in h.execute("SELECT source_ref FROM units WHERE source='vayo_all_nyc_units'")]
    print(f"classifying {len(refs)} vayo_all_nyc_units resolved rows by source_systems...", flush=True)
    vayo = sqlite3.connect(f"file:{VAYO_DB}?mode=ro", uri=True)
    result = {}
    BATCH = 1000
    for i in range(0, len(refs), BATCH):
        chunk = refs[i:i + BATCH]
        placeholders = ",".join("?" for _ in chunk)
        for unit_id, ss in vayo.execute(
            f"SELECT unit_id, source_systems FROM all_nyc_units WHERE unit_id IN ({placeholders})", chunk
        ):
            result[unit_id] = None if ss == '["PLUTO_INFERRED"]' else ss.strip('[]"').lower().replace("_", "_")
        if i % 200000 == 0:
            print(f"...{i}", flush=True)
    vayo.close()
    return result

def source_label(source, vayo_class):
    if source != "vayo_all_nyc_units":
        return f"archive_{source}"
    return f"vayo_{vayo_class}" if vayo_class else None  # None = synthetic, drop

def main():
    global H_DB, C_DB, VAYO_DB
    parser = argparse.ArgumentParser(description="Merge source-backed resolved archive units into a catalog.")
    parser.add_argument("--hierarchy-db", required=True, help="hierarchy SQLite path from build_hierarchy.py")
    parser.add_argument("--catalog-db", required=True, help="catalog SQLite path to update")
    parser.add_argument("--vayo-db", required=True, help="all_nyc_units archive SQLite path")
    args = parser.parse_args()
    H_DB, C_DB, VAYO_DB = args.hierarchy_db, args.catalog_db, args.vayo_db
    h = sqlite3.connect(H_DB)
    vayo_class = classify_vayo(h)

    c = sqlite3.connect(C_DB)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")

    seen_sources = set()
    kept = dropped_synthetic = 0
    now = _now()

    obs_buf, match_buf, unit_buf, src_buf = [], [], [], []
    BATCH = 20000

    def flush():
        nonlocal obs_buf, match_buf, unit_buf, src_buf
        if src_buf:
            c.executemany(
                "INSERT OR IGNORE INTO sources (source,source_kind,methodology,first_seen,last_seen) VALUES (?,?,?,?,?)",
                src_buf)
        if unit_buf:
            c.executemany(
                "INSERT INTO units (unit_id,bbl,unit_label,normalized_unit,first_seen,last_seen) VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(bbl,normalized_unit) DO UPDATE SET last_seen=excluded.last_seen",
                unit_buf)
        if obs_buf:
            c.executemany(
                "INSERT INTO observations (observation_id,document_id,source,source_ref,observed_at,observation_kind,"
                "address,unit_label,evidence_grade) VALUES (?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(source,source_ref,observed_at,observation_kind) DO NOTHING",
                obs_buf)
        if match_buf:
            c.executemany(
                "INSERT INTO entity_matches (observation_id,entity_type,entity_id,status,confidence,method,rationale,matched_at) "
                "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(observation_id,entity_type) DO NOTHING",
                match_buf)
        c.commit()
        obs_buf, match_buf, unit_buf, src_buf = [], [], [], []

    n = 0
    for source, bbl, unit_norm, raw_address, raw_unit, source_ref, resolved_via in h.execute(
        "SELECT source, bbl, unit_normalized, raw_address, raw_unit, source_ref, resolved_via FROM units"
    ):
        n += 1
        label = source_label(source, vayo_class.get(source_ref) if source == "vayo_all_nyc_units" else None)
        if not label:
            dropped_synthetic += 1
            continue
        kept += 1

        if label not in seen_sources:
            seen_sources.add(label)
            src_buf.append((label, "archived_secondary_source",
                             f"identity-only merge from raw {source} archive extraction; no price/observation date, "
                             f"resolved via {resolved_via}", now, now))

        unit_id = _id("unit", bbl, unit_norm)
        unit_buf.append((unit_id, bbl, raw_unit or unit_norm, unit_norm, now, now))

        observation_id = _id("obs", label, source_ref, "archive_identity_evidence")
        obs_buf.append((observation_id, None, label, str(source_ref), now, "archive_identity_evidence",
                         raw_address, raw_unit, "legacy_snapshot"))

        match_buf.append((observation_id, "building", bbl, "resolved", 1.0, resolved_via,
                           f"raw archive address resolved to official BBL via {resolved_via}", now))
        match_buf.append((observation_id, "unit", unit_id, "resolved", 1.0, resolved_via,
                           f"raw archive unit label resolved via {resolved_via}", now))

        if n % BATCH == 0:
            flush()
        if n % 500000 == 0:
            print(f"...{n} processed (kept={kept} dropped_synthetic={dropped_synthetic})", flush=True)

    flush()
    print(f"DONE. processed={n} kept={kept} dropped_synthetic={dropped_synthetic}")
    print("sources merged:", sorted(seen_sources))

if __name__ == "__main__":
    main()
