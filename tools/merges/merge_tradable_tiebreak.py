#!/usr/bin/env python3
"""Resolve ambiguous rows where exactly one candidate BBL has residential units
(PLUTO units_res>0) -- the "tradable" one, e.g. the actual building vs. a garage or
parking annex sharing its civic address. Same PLUTO_INFERRED exclusion as before so
no synthetic vayo rows sneak in. Merges survivors into catalog.db with real sources.
"""
import argparse
import sqlite3
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.engine.dedupe import normalize_unit

H_DB = None
C_DB = None
VAYO_DB = None

def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())

def _id(*parts):
    return uuid.uuid5(uuid.NAMESPACE_URL, "|".join(str(p) for p in parts)).hex[:20]

def classify_vayo_refs(refs):
    """source_ref -> real source label, or None if PLUTO_INFERRED-only (synthetic)."""
    if not refs:
        return {}
    print(f"classifying {len(refs)} vayo source_refs...", flush=True)
    vayo = sqlite3.connect(f"file:{VAYO_DB}?mode=ro", uri=True)
    result = {}
    BATCH = 1000
    refs = list(refs)
    for i in range(0, len(refs), BATCH):
        chunk = refs[i:i + BATCH]
        placeholders = ",".join("?" for _ in chunk)
        for unit_id, ss in vayo.execute(
            f"SELECT unit_id, source_systems FROM all_nyc_units WHERE unit_id IN ({placeholders})", chunk
        ):
            result[unit_id] = None if ss == '["PLUTO_INFERRED"]' else ss.strip('[]"').lower()
        if i % 200000 == 0:
            print(f"...{i}", flush=True)
    vayo.close()
    return result

def real_source_label(source, source_ref, vayo_class):
    """Base label (before the _tradable_tiebreak suffix), or None if synthetic."""
    if source != "vayo_all_nyc_units":
        return f"archive_{source}"
    cls = vayo_class.get(source_ref)
    return f"vayo_{cls}" if cls else None

def main():
    global H_DB, C_DB, VAYO_DB
    parser = argparse.ArgumentParser(description="Resolve archive ambiguity when one BBL is residential.")
    parser.add_argument("--hierarchy-db", required=True, help="hierarchy SQLite path from build_hierarchy.py")
    parser.add_argument("--catalog-db", required=True, help="catalog SQLite path to update")
    parser.add_argument("--vayo-db", required=True, help="all_nyc_units archive SQLite path")
    args = parser.parse_args()
    H_DB, C_DB, VAYO_DB = args.hierarchy_db, args.catalog_db, args.vayo_db
    h = sqlite3.connect(H_DB)
    c = sqlite3.connect(C_DB)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")

    units_res = dict(c.execute("SELECT bbl, units_res FROM buildings").fetchall())

    resolvable = []  # (source, raw_address, raw_unit, source_ref, winning_bbl)
    vayo_refs = set()
    n = still_ambig = all_nonres = 0
    for source, raw_address, raw_unit, source_ref, bbls_str in h.execute(
        "SELECT source, raw_address, raw_unit, source_ref, candidate_bbls FROM ambiguous"
    ):
        n += 1
        bbls = bbls_str.split(",")
        residential = [b for b in bbls if (units_res.get(b) or 0) > 0]
        if len(residential) != 1:
            if len(residential) == 0:
                all_nonres += 1
            else:
                still_ambig += 1
            continue
        resolvable.append((source, raw_address, raw_unit, source_ref, residential[0]))
        if source == "vayo_all_nyc_units":
            vayo_refs.add(source_ref)
        if n % 500000 == 0:
            print(f"scanned {n}, resolvable so far {len(resolvable)}", flush=True)

    print(f"scan done: total={n} resolvable={len(resolvable)} still_ambiguous={still_ambig} all_nonresidential={all_nonres}")
    vayo_class = classify_vayo_refs(vayo_refs)

    seen_sources = set()
    kept = dropped_synthetic = 0
    now = _now()
    unit_buf, obs_buf, match_buf, src_buf = [], [], [], []
    BATCH = 20000

    def flush():
        nonlocal unit_buf, obs_buf, match_buf, src_buf
        if src_buf:
            c.executemany(
                "INSERT OR IGNORE INTO sources (source,source_kind,methodology,first_seen,last_seen) VALUES (?,?,?,?,?)",
                src_buf)
        if unit_buf:
            c.executemany(
                "INSERT INTO units (unit_id,bbl,unit_label,normalized_unit,first_seen,last_seen) VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(bbl,normalized_unit) DO UPDATE SET last_seen=excluded.last_seen", unit_buf)
        if obs_buf:
            c.executemany(
                "INSERT INTO observations (observation_id,document_id,source,source_ref,observed_at,observation_kind,"
                "address,unit_label,evidence_grade) VALUES (?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(source,source_ref,observed_at,observation_kind) DO NOTHING", obs_buf)
        if match_buf:
            c.executemany(
                "INSERT INTO entity_matches (observation_id,entity_type,entity_id,status,confidence,method,rationale,matched_at) "
                "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(observation_id,entity_type) DO NOTHING", match_buf)
        c.commit()
        unit_buf, obs_buf, match_buf, src_buf = [], [], [], []

    for i, (source, raw_address, raw_unit, source_ref, bbl) in enumerate(resolvable, 1):
        base_label = real_source_label(source, source_ref, vayo_class)
        if not base_label:
            dropped_synthetic += 1
            continue
        kept += 1
        label = base_label + "_tradable_tiebreak"

        if label not in seen_sources:
            seen_sources.add(label)
            src_buf.append((label, "derived_inference",
                             f"resolved from a multi-BBL-candidate address by keeping the one residential "
                             f"(PLUTO units_res>0) candidate over non-residential siblings (garage/parking/"
                             f"commercial annex sharing the civic address); original source {source}",
                             now, now))

        unit_norm = normalize_unit(raw_unit)
        unit_id = _id("unit", bbl, unit_norm)
        unit_buf.append((unit_id, bbl, raw_unit, unit_norm, now, now))

        observation_id = _id("obs", label, source_ref, "archive_identity_evidence_tiebreak")
        obs_buf.append((observation_id, None, label, str(source_ref), now, "archive_identity_evidence_tiebreak",
                         raw_address, raw_unit, "derived_inference"))

        match_buf.append((observation_id, "building", bbl, "resolved", 0.9, "residential_tradable_tiebreak",
                           "one of multiple candidate BBLs was residential (PLUTO units_res>0), the rest were not",
                           now))
        match_buf.append((observation_id, "unit", unit_id, "resolved", 0.9, "residential_tradable_tiebreak",
                           "unit attached to the sole residential candidate BBL", now))

        if i % BATCH == 0:
            flush()
        if i % 500000 == 0:
            print(f"...{i} merged (kept={kept} dropped_synthetic={dropped_synthetic})", flush=True)

    flush()
    print(f"DONE. resolvable={len(resolvable)} kept={kept} dropped_synthetic={dropped_synthetic}")
    print("sources merged:", sorted(seen_sources))
    print("total units now:", c.execute("SELECT COUNT(*) FROM units").fetchone()[0])

if __name__ == "__main__":
    main()
