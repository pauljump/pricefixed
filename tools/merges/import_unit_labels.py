#!/usr/bin/env python3
"""Import manually reviewed unit labels from public occupancy documents.

Input CSV columns: address, bbl, unit_label, source_ref, source_url, observed_at.
The importer requires the document's address to exactly match an official catalog
address on the supplied BBL. This is load-bearing for tax lots such as Stuyvesant
Town and Peter Cooper Village, where one BBL covers many addresses. The importer
rejects missing source references, malformed BBLs, non-catalog addresses, and
common-area labels. It never creates a row from a count alone or from a BBL-only
label.
"""
import argparse
import csv
import hashlib
import json
import sqlite3
import time

from pricefixed.engine.crosswalk import normalize_address
from pricefixed.engine.dedupe import normalize_unit
from pricefixed.engine.identifiers import normalize_bbl

SOURCE = "dob_occupancy_document_labels"
NON_DWELLING = {"BASEMENT", "CELLAR", "ROOF", "HALLWAY", "PUBLIC HALL", "PUBLIC AREA", "STAIRWAY", "STAIRWELL",
                "ELEVATOR", "ENTIRE BUILDING", "BUILDING", "PARKING", "STORAGE", "OFFICE"}
NON_DWELLING_NORMALIZED = {normalize_unit(label) for label in NON_DWELLING}


def stable_id(prefix, *parts):
    value = "\x1f".join(str(part or "") for part in parts)
    return prefix + "_" + hashlib.sha256(value.encode()).hexdigest()[:20]


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())


def _official_address(conn, bbl, address):
    normalized = normalize_address(address)
    if not normalized:
        return None, "invalid_address"
    row = conn.execute(
        "SELECT address,normalized,zipcode,source FROM addresses WHERE bbl=? AND normalized=?",
        (bbl, normalized),
    ).fetchone()
    if not row:
        return None, "address_not_in_catalog_bbl"
    return row, ""


def import_labels(conn, rows, stamp=None):
    """Import validated reviewed rows and return imported/rejected details."""
    stamp = stamp or now()
    conn.execute(
        "INSERT INTO sources (source,source_kind,methodology,first_seen,last_seen) VALUES (?,?,?,?,?) "
        "ON CONFLICT(source) DO UPDATE SET last_seen=excluded.last_seen",
        (SOURCE, "public_record", "Human-reviewed unit labels transcribed from a public DOB occupancy document; "
         "counts without labels or exact catalog addresses are rejected.", stamp, stamp),
    )
    imported = []
    rejected = []
    for input_row in rows:
        row = dict(input_row)
        address = str(row.get("address") or "").strip()
        raw_bbl = str(row.get("bbl") or "").strip()
        label = str(row.get("unit_label") or "").strip()
        source_ref = str(row.get("source_ref") or "").strip()
        source_url = str(row.get("source_url") or "").strip()
        observed_at = str(row.get("observed_at") or stamp[:10]).strip()
        bbl = normalize_bbl(raw_bbl)
        normalized_label = normalize_unit(label)
        reason = ""
        if not address or not bbl or not label or not source_ref or not source_url:
            reason = "missing_or_malformed_required_field"
        elif normalized_label in NON_DWELLING_NORMALIZED:
            reason = "non_dwelling_label"
        else:
            official, reason = _official_address(conn, bbl, address)
        if reason:
            row["rejection_reason"] = reason
            rejected.append(row)
            continue

        official_address, normalized_address, zipcode, address_source = official
        normalized_source_address = normalized_address
        document_id = stable_id("doc", SOURCE, source_ref)
        observation_ref = f"{source_ref}#address={normalized_source_address}#unit={normalized_label}"
        observation_id = stable_id("obs", SOURCE, observation_ref)
        premise_id = stable_id("premise", bbl, normalized_source_address)
        unit_id = stable_id("unit", bbl, normalized_label)
        addressable_unit_id = stable_id("addressable_unit", premise_id, normalized_label)
        payload = json.dumps({
            "address": address,
            "bbl": bbl,
            "unit_label": label,
            "source_ref": source_ref,
            "source_url": source_url,
            "observed_at": observed_at,
        }, sort_keys=True)
        conn.execute(
            "INSERT OR IGNORE INTO source_documents "
            "(document_id,source,source_ref,retrieved_at,payload,payload_kind) VALUES (?,?,?,?,?,?)",
            (document_id, SOURCE, source_ref, stamp, payload, "reviewed_public_document_reference"),
        )
        conn.execute(
            "INSERT INTO premises (premise_id,bbl,address,normalized,zipcode,source,first_seen,last_seen) "
            "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(bbl,normalized) DO UPDATE SET "
            "address=excluded.address,zipcode=excluded.zipcode,last_seen=excluded.last_seen",
            (premise_id, bbl, official_address, normalized_source_address, zipcode,
             address_source or "catalog_address", stamp, stamp),
        )
        conn.execute(
            "INSERT INTO units (unit_id,bbl,unit_label,normalized_unit,first_seen,last_seen) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(bbl,normalized_unit) DO UPDATE SET "
            "unit_label=excluded.unit_label,last_seen=excluded.last_seen",
            (unit_id, bbl, label, normalized_label, stamp, stamp),
        )
        conn.execute(
            "INSERT INTO addressable_units "
            "(addressable_unit_id,premise_id,unit_label,normalized_unit,first_seen,last_seen) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(premise_id,normalized_unit) DO UPDATE SET "
            "unit_label=excluded.unit_label,last_seen=excluded.last_seen",
            (addressable_unit_id, premise_id, label, normalized_label, stamp, stamp),
        )
        conn.execute(
            "INSERT INTO observations "
            "(observation_id,document_id,source,source_ref,observed_at,observation_kind,address,unit_label,raw_fields,evidence_grade) "
            "VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source,source_ref,observed_at,observation_kind) DO UPDATE SET "
            "document_id=excluded.document_id,address=excluded.address,unit_label=excluded.unit_label,"
            "raw_fields=excluded.raw_fields,evidence_grade=excluded.evidence_grade",
            (observation_id, document_id, SOURCE, observation_ref, observed_at,
             "official_unit_label", official_address, label, payload, "source_document"),
        )
        conn.execute(
            "INSERT INTO entity_matches "
            "(observation_id,entity_type,entity_id,status,confidence,method,rationale,matched_at) "
            "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(observation_id,entity_type) DO UPDATE SET "
            "entity_id=excluded.entity_id,status=excluded.status,confidence=excluded.confidence,"
            "method=excluded.method,rationale=excluded.rationale,matched_at=excluded.matched_at",
            (observation_id, "unit", unit_id, "resolved", 1.0,
             "reviewed_document_exact_catalog_address_and_unit_label",
             "Reviewed public document supplies an exact official address on the BBL and a unit label.", stamp),
        )
        conn.execute(
            "INSERT INTO entity_matches "
            "(observation_id,entity_type,entity_id,status,confidence,method,rationale,matched_at) "
            "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(observation_id,entity_type) DO UPDATE SET "
            "entity_id=excluded.entity_id,status=excluded.status,confidence=excluded.confidence,"
            "method=excluded.method,rationale=excluded.rationale,matched_at=excluded.matched_at",
            (observation_id, "addressable_unit", addressable_unit_id, "resolved", 1.0,
             "reviewed_document_exact_catalog_address_and_unit_label",
             "Reviewed public document supplies the premise address and unit label.", stamp),
        )
        imported.append(row)
    conn.commit()
    return {"imported": imported, "rejected": rejected}


def main():
    parser = argparse.ArgumentParser(description="Import reviewed unit labels with document provenance.")
    parser.add_argument("--catalog-db", required=True)
    parser.add_argument("--csv", required=True)
    parser.add_argument(
        "--rejected",
        help="CSV path for rejected rows; defaults to <input>.rejected.csv",
    )
    args = parser.parse_args()
    conn = sqlite3.connect(args.catalog_db)
    conn.execute("PRAGMA busy_timeout=30000")
    with open(args.csv, encoding="utf-8", newline="") as handle:
        result = import_labels(conn, csv.DictReader(handle))
    rejected_path = args.rejected or (args.csv + ".rejected.csv")
    rejected_rows = result["rejected"]
    fields = sorted({key for row in rejected_rows for key in row}) if rejected_rows else [
        "address", "bbl", "unit_label", "source_ref", "source_url", "observed_at", "rejection_reason"
    ]
    with open(rejected_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rejected_rows)
    print(f"imported labels: {len(result['imported'])}")
    print(f"rejected rows: {len(rejected_rows)}")
    print(f"wrote rejected rows: {rejected_path}")


if __name__ == "__main__":
    main()
