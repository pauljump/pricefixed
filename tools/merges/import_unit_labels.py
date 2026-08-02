#!/usr/bin/env python3
"""Import manually reviewed unit labels from public occupancy documents.

Input CSV columns: bbl, unit_label, source_ref, source_url, observed_at.
The importer rejects missing source references, malformed BBLs, and common-area
labels. It never creates a row from a count alone.
"""
import argparse
import csv
import hashlib
import json
import re
import sqlite3
import time

SOURCE = "dob_occupancy_document_labels"
NON_DWELLING = {"BASEMENT", "CELLAR", "ROOF", "HALLWAY", "STAIRWAY", "STAIRWELL",
                "ELEVATOR", "ENTIRE BUILDING", "BUILDING", "PARKING", "STORAGE", "OFFICE"}


def stable_id(prefix, *parts):
    value = "\x1f".join(str(part or "") for part in parts)
    return prefix + "_" + hashlib.sha256(value.encode()).hexdigest()[:20]


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())


def main():
    parser = argparse.ArgumentParser(description="Import reviewed unit labels with document provenance.")
    parser.add_argument("--catalog-db", required=True)
    parser.add_argument("--csv", required=True)
    args = parser.parse_args()
    conn = sqlite3.connect(args.catalog_db)
    conn.execute("PRAGMA busy_timeout=30000")
    stamp = now()
    conn.execute(
        "INSERT INTO sources (source,source_kind,methodology,first_seen,last_seen) VALUES (?,?,?,?,?) "
        "ON CONFLICT(source) DO UPDATE SET last_seen=excluded.last_seen",
        (SOURCE, "public_record", "Human-reviewed unit labels transcribed from a public DOB occupancy document; "
         "counts without labels are rejected.", stamp, stamp),
    )
    imported = 0
    rejected = 0
    with open(args.csv, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            bbl = str(row.get("bbl") or "").strip()
            label = str(row.get("unit_label") or "").strip()
            source_ref = str(row.get("source_ref") or "").strip()
            source_url = str(row.get("source_url") or "").strip()
            observed_at = str(row.get("observed_at") or stamp[:10]).strip()
            if not re.fullmatch(r"[1-5]\d{9}", bbl) or not label or not source_ref or not source_url:
                rejected += 1
                continue
            if label.upper() in NON_DWELLING:
                rejected += 1
                continue
            payload = json.dumps({"bbl": bbl, "unit_label": label, "source_ref": source_ref,
                                  "source_url": source_url, "observed_at": observed_at}, sort_keys=True)
            document_id = stable_id("doc", SOURCE, source_ref)
            observation_id = stable_id("obs", SOURCE, source_ref, label)
            unit_id = stable_id("unit", bbl, label.upper())
            normalized = re.sub(r"\s+", " ", label.upper())
            conn.execute("INSERT OR IGNORE INTO source_documents "
                         "(document_id,source,source_ref,retrieved_at,payload,payload_kind) VALUES (?,?,?,?,?,?)",
                         (document_id, SOURCE, source_ref, stamp, payload, "reviewed_public_document_reference"))
            conn.execute("INSERT INTO units (unit_id,bbl,unit_label,normalized_unit,first_seen,last_seen) "
                         "VALUES (?,?,?,?,?,?) ON CONFLICT(bbl,normalized_unit) DO UPDATE SET last_seen=excluded.last_seen",
                         (unit_id, bbl, label, normalized, stamp, stamp))
            conn.execute("INSERT INTO observations "
                         "(observation_id,document_id,source,source_ref,observed_at,observation_kind,unit_label,raw_fields,evidence_grade) "
                         "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(source,source_ref,observed_at,observation_kind) DO UPDATE SET "
                         "document_id=excluded.document_id,unit_label=excluded.unit_label,raw_fields=excluded.raw_fields",
                         (observation_id, document_id, SOURCE, source_ref, observed_at,
                          "official_unit_label", label, payload, "source_document"))
            conn.execute("INSERT INTO entity_matches "
                         "(observation_id,entity_type,entity_id,status,confidence,method,rationale,matched_at) "
                         "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(observation_id,entity_type) DO UPDATE SET "
                         "entity_id=excluded.entity_id,status=excluded.status,confidence=excluded.confidence",
                         (observation_id, "unit", unit_id, "resolved", 1.0, "reviewed_document_bbl_and_label",
                          "Human-reviewed public document supplies the BBL and unit label", stamp))
            imported += 1
    conn.commit()
    print(f"imported labels: {imported}")
    print(f"rejected rows: {rejected}")


if __name__ == "__main__":
    main()
