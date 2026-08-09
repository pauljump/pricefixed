#!/usr/bin/env python3
"""Merge validated DOF Statement-of-Account property addresses.

The address miner supplies a public tax-bill URL and a property address for an
official DOF condo unit-lot BBL. This merge only adds the address/premise bridge
for a unit identity that already exists in ``units`` and whose designation still
matches ``official_unit_lots``. It never creates a unit from an address alone.
"""
import argparse
import csv
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.engine.crosswalk import normalize_address
from pricefixed.engine.dedupe import normalize_unit
from pricefixed.engine.identifiers import normalize_bbl


SOURCE = "dof_statement_property_addresses"


def stable_id(prefix, *parts):
    material = "\x1f".join(str(part or "") for part in parts)
    return f"{prefix}_{hashlib.sha256(material.encode('utf-8')).hexdigest()[:20]}"


def statement_date(value):
    """Normalize YYYYMMDD statement dates while retaining the raw input."""
    raw = str(value or "").strip()
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return raw


def row_reasons(row, official, catalog_units):
    """Return deterministic rejection reasons for one validated CSV row."""
    bbl = normalize_bbl(row.get("unit_lot_bbl")) or ""
    address = normalize_address(row.get("address") or "")
    designation = normalize_unit(
        row.get("official_unit_designation") or row.get("unit_designation") or ""
    )
    reasons = []
    if row.get("validation_status") != "accepted":
        reasons.append("input_not_validated")
    if not bbl:
        reasons.append("invalid_unit_lot_bbl")
    if not address:
        reasons.append("empty_statement_address")
    if not row.get("source_url", "").startswith("https://"):
        reasons.append("missing_source_url")
    expected = official.get(bbl)
    if expected is None:
        reasons.append("not_in_official_unit_lots")
    elif designation != normalize_unit(expected):
        reasons.append("unit_designation_mismatch")
    if (bbl, designation) not in catalog_units:
        reasons.append("unit_identity_not_in_catalog")
    return reasons


def load_rows(path, catalog):
    official = {
        bbl: designation
        for bbl, designation in catalog.execute(
            "SELECT unit_lot_bbl,unit_designation FROM official_unit_lots"
        )
    }
    catalog_units = {
        (bbl, normalized)
        for bbl, normalized in catalog.execute(
            "SELECT bbl,normalized_unit FROM units"
        )
    }
    accepted, rejected = [], []
    with Path(path).open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            reasons = row_reasons(row, official, catalog_units)
            row = dict(row)
            row["unit_lot_bbl"] = normalize_bbl(row.get("unit_lot_bbl")) or ""
            row["address"] = " ".join(str(row.get("address") or "").split())
            row["official_unit_designation"] = official.get(row["unit_lot_bbl"], "")
            row["validation_status"] = "accepted" if not reasons else "rejected"
            row["validation_reason"] = ";".join(reasons)
            (accepted if not reasons else rejected).append(row)
    return accepted, rejected


def merge(catalog_path, input_path, rejected_path, summary_path, apply=False):
    catalog = sqlite3.connect(catalog_path)
    catalog.execute("PRAGMA busy_timeout=60000")
    try:
        accepted, rejected = load_rows(input_path, catalog)
        if rejected:
            fields = list(rejected[0])
            with Path(rejected_path).open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rejected)

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        new_bridges = 0
        if apply:
            catalog.execute("BEGIN")
            catalog.execute(
                "INSERT INTO sources(source,source_kind,methodology,first_seen,last_seen) "
                "VALUES (?,?,?,?,?) ON CONFLICT(source) DO UPDATE SET last_seen=excluded.last_seen",
                (SOURCE, "public_record",
                 "DOF Statement of Account property address joined to an existing official "
                 "condo unit-lot BBL and matching unit designation; address bridge only",
                 now, now),
            )
            for row in accepted:
                bbl = row["unit_lot_bbl"]
                designation = row["official_unit_designation"]
                normalized_unit = normalize_unit(designation)
                address = row["address"]
                normalized_address = normalize_address(address)
                observed_at = statement_date(row.get("statement_date")) or now[:10]
                source_ref = f"dof-soa-address:{bbl}:{row.get('statement_date') or observed_at}"
                document_id = stable_id("doc", SOURCE, source_ref)
                payload = json.dumps({
                    "unit_lot_bbl": bbl,
                    "unit_designation": designation,
                    "address": address,
                    "statement_date": row.get("statement_date", ""),
                    "source_url": row.get("source_url", ""),
                    "extraction_method": "pdftotext_property_address_regex",
                }, sort_keys=True)
                catalog.execute(
                    "INSERT OR IGNORE INTO source_documents "
                    "(document_id,source,source_ref,retrieved_at,payload,payload_kind) "
                    "VALUES (?,?,?,?,?,?)",
                    (document_id, SOURCE, source_ref, now, payload, "dof_statement_address"),
                )
                catalog.execute(
                    "INSERT OR IGNORE INTO buildings(bbl,source,first_seen,last_seen) "
                    "VALUES (?,?,?,?)", (bbl, SOURCE, now, now),
                )
                catalog.execute(
                    "INSERT OR IGNORE INTO addresses "
                    "(address_id,bbl,address,normalized,zipcode,source) VALUES (?,?,?,?,?,?)",
                    (stable_id("addr", bbl, normalized_address), bbl, address,
                     normalized_address, None, SOURCE),
                )
                catalog.execute(
                    "INSERT OR IGNORE INTO premises "
                    "(premise_id,bbl,address,normalized,zipcode,source,first_seen,last_seen) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (stable_id("premise", bbl, normalized_address), bbl, address,
                     normalized_address, None, SOURCE, now, now),
                )
                premise_id = catalog.execute(
                    "SELECT premise_id FROM premises WHERE bbl=? AND normalized=?",
                    (bbl, normalized_address),
                ).fetchone()[0]
                addressable_id = stable_id("addressable_unit", premise_id, normalized_unit)
                catalog.execute(
                    "INSERT OR IGNORE INTO addressable_units "
                    "(addressable_unit_id,premise_id,unit_label,normalized_unit,first_seen,last_seen) "
                    "VALUES (?,?,?,?,?,?)",
                    (addressable_id, premise_id, designation, normalized_unit, now, now),
                )
                unit_id = catalog.execute(
                    "SELECT unit_id FROM units WHERE bbl=? AND normalized_unit=?",
                    (bbl, normalized_unit),
                ).fetchone()[0]
                observation_id = stable_id("obs", SOURCE, source_ref, observed_at)
                catalog.execute(
                    "INSERT OR IGNORE INTO observations "
                    "(observation_id,document_id,source,source_ref,observed_at,observation_kind,"
                    "address,unit_label,status,raw_fields,evidence_grade) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (observation_id, document_id, SOURCE, source_ref, observed_at,
                     "dof_statement_property_address", address, designation, "reported",
                     payload, "source_document"),
                )
                rationale = "DOF statement address and official unit-lot designation agree"
                for entity_type, entity_id, method in (
                    ("building", bbl, "dof_statement_unit_lot_bbl"),
                    ("unit", unit_id, "dof_statement_official_unit_lot"),
                    ("addressable_unit", addressable_id, "dof_statement_property_address"),
                ):
                    catalog.execute(
                        "INSERT INTO entity_matches "
                        "(observation_id,entity_type,entity_id,status,confidence,method,rationale,matched_at) "
                        "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(observation_id,entity_type) DO UPDATE SET "
                        "entity_id=excluded.entity_id,status=excluded.status,confidence=excluded.confidence,"
                        "method=excluded.method,rationale=excluded.rationale,matched_at=excluded.matched_at",
                        (observation_id, entity_type, entity_id, "resolved", 1.0,
                         method, rationale, now),
                    )
                new_bridges += 1
            catalog.commit()
        summary = {
            "input_rows": len(accepted) + len(rejected),
            "accepted_rows": len(accepted),
            "rejected_rows": len(rejected),
            "catalog_writes": new_bridges,
            "apply": bool(apply),
        }
        Path(summary_path).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return summary
    finally:
        catalog.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-db", required=True)
    parser.add_argument("--input", required=True, help="CSV from validate_dof_unit_addresses.py")
    parser.add_argument("--rejected", default=None)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    rejected = args.rejected or f"{args.input}.merge-rejected.csv"
    summary = merge(args.catalog_db, args.input, rejected, args.summary, apply=args.apply)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
