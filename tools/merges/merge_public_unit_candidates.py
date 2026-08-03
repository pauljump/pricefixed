#!/usr/bin/env python3
"""Merge reviewed net-new units from compact official public-record mentions."""
import argparse
import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.engine.crosswalk import normalize_address


SOURCE_INFO = {
    "dob_jobs": ("dob_now_jobs_compact", "NYC DOB NOW job filings with direct BBL and apartment label"),
    "dob_permits": ("dob_now_permits_compact", "NYC DOB NOW permits with direct BBL and apartment label"),
    "hpd_problems": ("hpd_problems_compact", "NYC HPD problems with direct BBL and apartment label"),
    "hpd_violations": ("hpd_violations_compact", "NYC HPD violations with direct BBL and apartment label"),
    "hpd_omo": ("hpd_omo_compact", "NYC HPD emergency work orders with direct BBL and apartment label"),
    "nycha_violations": ("nycha_violations_compact", "NYCHA violations with direct BBL and inspected unit label"),
    "evictions": ("nyc_evictions_compact", "NYC executed evictions with direct BBL and apartment label"),
}


def stable_id(prefix, *parts):
    material = "\x1f".join(str(part or "") for part in parts)
    return f"{prefix}_{hashlib.sha256(material.encode('utf-8')).hexdigest()[:20]}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mentions-db", required=True)
    parser.add_argument("--catalog-db", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--batch-size", type=int, default=10000)
    args = parser.parse_args()
    source = sqlite3.connect(f"file:{Path(args.mentions_db).resolve()}?mode=ro", uri=True)
    count = source.execute("SELECT COUNT(*) FROM unit_candidates WHERE exists_in_catalog=0").fetchone()[0]
    by_source = source.execute(
        "SELECT source,COUNT(*) FROM unit_candidates WHERE exists_in_catalog=0 GROUP BY source ORDER BY source"
    ).fetchall()
    print(f"net-new candidates: {count}")
    for name, rows in by_source:
        print(f"  {name}: {rows}")
    if not args.apply:
        print("dry run only; pass --apply to update the catalog")
        return

    catalog = sqlite3.connect(args.catalog_db)
    catalog.execute("PRAGMA journal_mode=WAL")
    catalog.execute("PRAGMA busy_timeout=60000")
    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    for name, (catalog_source, methodology) in SOURCE_INFO.items():
        catalog.execute(
            "INSERT INTO sources(source,source_kind,methodology,first_seen,last_seen) VALUES (?,?,?,?,?) "
            "ON CONFLICT(source) DO UPDATE SET last_seen=excluded.last_seen",
            (catalog_source, "public_record", methodology + "; compact dedup keeps one representative record per unit.",
             stamp, stamp),
        )
    rows = source.execute(
        "SELECT bbl,normalized_unit,unit_label,address,zipcode,source,source_ref,observed_at,dataset,source_url "
        "FROM unit_candidates WHERE exists_in_catalog=0 ORDER BY rowid"
    )
    imported = 0
    for row in rows:
        bbl, normalized_unit, label, address, zipcode, short_source, upstream_ref, observed_at, dataset, source_url = row
        catalog_source = SOURCE_INFO[short_source][0]
        source_ref = stable_id("compact_ref", dataset, upstream_ref, bbl, normalized_unit)
        document_id = stable_id("doc", catalog_source, source_ref)
        observation_id = stable_id("obs", catalog_source, source_ref, "official_unit_mention")
        unit_id = stable_id("unit", bbl, normalized_unit)
        payload = json.dumps({
            "dataset": dataset, "upstream_source_ref": upstream_ref, "bbl": bbl,
            "address": address, "zipcode": zipcode, "unit_label": label,
            "observed_at": observed_at, "source_url": source_url,
        }, sort_keys=True)
        catalog.execute(
            "INSERT OR IGNORE INTO source_documents "
            "(document_id,source,source_ref,retrieved_at,payload,payload_kind) VALUES (?,?,?,?,?,?)",
            (document_id, catalog_source, source_ref, stamp, payload, "deduplicated_nyc_open_data_row"),
        )
        catalog.execute(
            "INSERT OR IGNORE INTO buildings "
            "(bbl,source,first_seen,last_seen) VALUES (?,?,?,?)", (bbl, catalog_source, stamp, stamp),
        )
        normalized_address = normalize_address(address)
        if normalized_address:
            catalog.execute(
                "INSERT INTO addresses(address_id,bbl,address,normalized,zipcode,source) VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(bbl,normalized) DO UPDATE SET address=excluded.address,zipcode=excluded.zipcode",
                (stable_id("addr", bbl, normalized_address), bbl, address, normalized_address, zipcode, catalog_source),
            )
        catalog.execute(
            "INSERT INTO units(unit_id,bbl,unit_label,normalized_unit,first_seen,last_seen) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(bbl,normalized_unit) DO UPDATE SET last_seen=excluded.last_seen",
            (unit_id, bbl, label, normalized_unit, stamp, stamp),
        )
        catalog.execute(
            "INSERT INTO observations "
            "(observation_id,document_id,source,source_ref,observed_at,observation_kind,address,unit_label,"
            "status,raw_fields,evidence_grade) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(source,source_ref,observed_at,observation_kind) DO NOTHING",
            (observation_id, document_id, catalog_source, source_ref, observed_at or stamp[:10],
             "official_unit_mention", address, label, "reported", payload, "source_document"),
        )
        catalog.execute(
            "INSERT INTO entity_matches "
            "(observation_id,entity_type,entity_id,status,confidence,method,rationale,matched_at) "
            "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(observation_id,entity_type) DO NOTHING",
            (observation_id, "building", bbl, "resolved", 1.0, "official_bbl",
             "The public agency record supplies the BBL", stamp),
        )
        catalog.execute(
            "INSERT INTO entity_matches "
            "(observation_id,entity_type,entity_id,status,confidence,method,rationale,matched_at) "
            "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(observation_id,entity_type) DO NOTHING",
            (observation_id, "unit", unit_id, "resolved", 1.0, "official_bbl_and_unit_label",
             "The public agency record supplies both BBL and apartment label", stamp),
        )
        if normalized_address:
            premise_id = stable_id("premise", bbl, normalized_address)
            addressable_id = stable_id("addressable_unit", premise_id, normalized_unit)
            catalog.execute(
                "INSERT INTO premises(premise_id,bbl,address,normalized,zipcode,source,first_seen,last_seen) "
                "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(bbl,normalized) DO UPDATE SET last_seen=excluded.last_seen",
                (premise_id, bbl, address, normalized_address, zipcode, catalog_source, stamp, stamp),
            )
            catalog.execute(
                "INSERT INTO addressable_units "
                "(addressable_unit_id,premise_id,unit_label,normalized_unit,first_seen,last_seen) "
                "VALUES (?,?,?,?,?,?) ON CONFLICT(premise_id,normalized_unit) DO UPDATE SET last_seen=excluded.last_seen",
                (addressable_id, premise_id, label, normalized_unit, stamp, stamp),
            )
            catalog.execute(
                "INSERT INTO entity_matches "
                "(observation_id,entity_type,entity_id,status,confidence,method,rationale,matched_at) "
                "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(observation_id,entity_type) DO NOTHING",
                (observation_id, "addressable_unit", addressable_id, "resolved", 1.0,
                 "official_bbl_address_and_unit_label",
                 "The public agency record supplies BBL, address, and apartment label", stamp),
            )
        imported += 1
        if imported % args.batch_size == 0:
            catalog.commit()
            print(f"imported {imported}/{count}", flush=True)
    catalog.commit()
    print(f"imported {imported} net-new units")
    source.close()
    catalog.close()


if __name__ == "__main__":
    main()
