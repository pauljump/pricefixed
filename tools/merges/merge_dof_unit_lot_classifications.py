#!/usr/bin/env python3
"""Apply reviewed DOF tax classes and unit addresses to the housing catalog."""
import argparse
import csv
import hashlib
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.engine.crosswalk import normalize_address
from pricefixed.engine.dedupe import normalize_unit


DATE_RE = re.compile(r"stmtDate=(\d{4})(\d{2})(\d{2})")


def stable_id(prefix, *parts):
    material = "\x1f".join(str(part or "") for part in parts)
    return f"{prefix}_{hashlib.sha256(material.encode('utf-8')).hexdigest()[:20]}"


def statement_date(url):
    match = DATE_RE.search(str(url or ""))
    return "-".join(match.groups()) if match else ""


def load_rows(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--classifications", required=True)
    parser.add_argument("--baseline-classifications", help="apply only rows whose classification changed")
    parser.add_argument("--addresses", help="validated DOF Statement address CSV")
    parser.add_argument("--catalog-db", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    rows = load_rows(args.classifications)
    if args.baseline_classifications:
        baseline = {
            row["unit_lot_bbl"]: row.get("classification", "")
            for row in load_rows(args.baseline_classifications)
        }
        rows = [
            row for row in rows
            if row.get("classification", "") != baseline.get(row["unit_lot_bbl"], "")
        ]
    address_evidence = {}
    if args.addresses:
        for row in load_rows(args.addresses):
            if row.get("validation_status") and row["validation_status"] != "accepted":
                continue
            if normalize_address(row.get("address")):
                address_evidence[row["unit_lot_bbl"]] = row
    residential = [row for row in rows if row["classification"] == "residential_tax_class"]
    nonresidential = [row for row in rows if row["classification"] == "nonresidential_tax_class"]
    missing = [row for row in rows if row["classification"] == "tax_class_not_found"]
    residential_addresses = [
        row for row in residential
        if normalize_address(
            address_evidence.get(row["unit_lot_bbl"], {}).get("address") or
            row.get("address") or row.get("assessment_address")
        )
    ]

    catalog = sqlite3.connect(args.catalog_db)
    catalog.execute("PRAGMA busy_timeout=60000")
    nonres_bbls = [row["unit_lot_bbl"] for row in nonresidential]
    existing_nonres_units = 0
    existing_nonres_addressable = 0
    if nonres_bbls:
        for start in range(0, len(nonres_bbls), 500):
            chunk = nonres_bbls[start:start + 500]
            marks = ",".join("?" for _ in chunk)
            existing_nonres_units += catalog.execute(
                f"SELECT COUNT(*) FROM units WHERE bbl IN ({marks})", chunk
            ).fetchone()[0]
            existing_nonres_addressable += catalog.execute(
                f"SELECT COUNT(*) FROM addressable_units au JOIN premises p USING(premise_id) "
                f"WHERE p.bbl IN ({marks})", chunk
            ).fetchone()[0]

    summary = {
        "input_unit_lots": len(rows),
        "validated_statement_addresses": len(address_evidence),
        "residential_unit_lots": len(residential),
        "residential_unit_lots_with_official_address": len(residential_addresses),
        "nonresidential_unit_lots": len(nonresidential),
        "unclassified_unit_lots": len(missing),
        "existing_nonresidential_units_to_remove": existing_nonres_units,
        "existing_nonresidential_addressable_units_to_remove": existing_nonres_addressable,
        "catalog_writes": 0,
    }
    if not args.apply:
        Path(args.summary).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        catalog.close()
        return

    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    catalog.execute("PRAGMA journal_mode=WAL")
    catalog.execute("BEGIN")
    catalog.execute(
        "INSERT INTO sources(source,source_kind,methodology,first_seen,last_seen) VALUES (?,?,?,?,?) "
        "ON CONFLICT(source) DO UPDATE SET last_seen=excluded.last_seen",
        ("dof_property_assessment_bulk", "public_record",
         "NYC DOF 2027 final assessment roll used to exclude nonresidential condo tax lots", stamp, stamp),
    )
    catalog.execute(
        "INSERT INTO sources(source,source_kind,methodology,first_seen,last_seen) VALUES (?,?,?,?,?) "
        "ON CONFLICT(source) DO UPDATE SET last_seen=excluded.last_seen",
        ("dof_statement_of_account", "public_record",
         "NYC DOF Statement of Account property address for an official condo unit-lot BBL", stamp, stamp),
    )

    removed_units = removed_addressable = 0
    for start in range(0, len(nonres_bbls), 500):
        chunk = nonres_bbls[start:start + 500]
        marks = ",".join("?" for _ in chunk)
        unit_ids = [row[0] for row in catalog.execute(
            f"SELECT unit_id FROM units WHERE bbl IN ({marks})", chunk
        )]
        premise_ids = [row[0] for row in catalog.execute(
            f"SELECT premise_id FROM premises WHERE bbl IN ({marks})", chunk
        )]
        addressable_ids = []
        if premise_ids:
            for pstart in range(0, len(premise_ids), 500):
                pchunk = premise_ids[pstart:pstart + 500]
                pmarks = ",".join("?" for _ in pchunk)
                addressable_ids.extend(row[0] for row in catalog.execute(
                    f"SELECT addressable_unit_id FROM addressable_units WHERE premise_id IN ({pmarks})", pchunk
                ))
        rationale = "DOF 2027 final assessment classifies this individual condo tax lot as tax class 4"
        for ids, entity_type in ((unit_ids, "unit"), (addressable_ids, "addressable_unit")):
            for istart in range(0, len(ids), 500):
                ichunk = ids[istart:istart + 500]
                imarks = ",".join("?" for _ in ichunk)
                catalog.execute(
                    f"UPDATE entity_matches SET entity_id=NULL,status='not_a_dwelling',confidence=0,"
                    f"method='official_tax_class_filter',rationale=?,matched_at=? "
                    f"WHERE entity_type=? AND entity_id IN ({imarks})",
                    [rationale, stamp, entity_type, *ichunk],
                )
        if addressable_ids:
            for istart in range(0, len(addressable_ids), 500):
                ichunk = addressable_ids[istart:istart + 500]
                imarks = ",".join("?" for _ in ichunk)
                removed_addressable += catalog.execute(
                    f"DELETE FROM addressable_units WHERE addressable_unit_id IN ({imarks})", ichunk
                ).rowcount
        catalog.execute(
            f"UPDATE official_unit_lot_links SET unit_id=NULL,status='not_a_dwelling',confidence=0,"
            f"method='official_tax_class_filter',rationale=? WHERE unit_lot_bbl IN ({marks})",
            [rationale, *chunk],
        )
        removed_units += catalog.execute(
            f"DELETE FROM units WHERE bbl IN ({marks})", chunk
        ).rowcount

    imported_units = imported_addresses = 0
    for row in residential:
        bbl = row["unit_lot_bbl"]
        label = row.get("official_unit_designation", "")
        normalized_unit = normalize_unit(label)
        if not normalized_unit:
            continue
        unit_id = stable_id("unit", bbl, normalized_unit)
        before = catalog.total_changes
        catalog.execute(
            "INSERT INTO units(unit_id,bbl,unit_label,normalized_unit,first_seen,last_seen) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(bbl,normalized_unit) DO UPDATE SET last_seen=excluded.last_seen",
            (unit_id, bbl, label, normalized_unit, stamp, stamp),
        )
        imported_units += int(catalog.total_changes > before)
        unit_id = catalog.execute(
            "SELECT unit_id FROM units WHERE bbl=? AND normalized_unit=?", (bbl, normalized_unit)
        ).fetchone()[0]
        address_row = address_evidence.get(bbl, row)
        address = address_row.get("address") or row.get("address") or row.get("assessment_address", "")
        normalized = normalize_address(address)
        if not normalized:
            continue
        statement_url = address_row.get("source_url") or row.get("address_source_url", "")
        source_url = statement_url or row.get("assessment_source_url", "")
        address_catalog_source = (
            "dof_statement_of_account" if statement_url else "dof_property_assessment_bulk"
        )
        observed_at = statement_date(source_url) or stamp[:10]
        source_ref = stable_id("dof_unit_address", bbl, observed_at, address_catalog_source)
        document_id = stable_id("doc", address_catalog_source, source_ref)
        observation_id = stable_id("obs", address_catalog_source, source_ref, "unit_lot_address")
        payload = json.dumps({
            "unit_lot_bbl": bbl, "unit_designation": label, "address": address,
            "address_source_url": source_url, "assessment_year": row.get("assessment_year"),
            "tax_class": row.get("tax_class"), "building_class": row.get("building_class"),
            "assessment_source_url": row.get("assessment_source_url"),
        }, sort_keys=True)
        catalog.execute(
            "INSERT OR IGNORE INTO source_documents(document_id,source,source_ref,retrieved_at,payload,payload_kind) "
            "VALUES (?,?,?,?,?,?)",
            (document_id, address_catalog_source, source_ref, stamp, payload, "extracted_public_record_fields"),
        )
        catalog.execute(
            "INSERT INTO buildings(bbl,source,first_seen,last_seen) VALUES (?,?,?,?) "
            "ON CONFLICT(bbl) DO UPDATE SET last_seen=excluded.last_seen",
            (bbl, address_catalog_source, stamp, stamp),
        )
        catalog.execute(
            "INSERT INTO addresses(address_id,bbl,address,normalized,zipcode,source) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(bbl,normalized) DO UPDATE SET address=excluded.address,zipcode=excluded.zipcode",
            (stable_id("addr", bbl, normalized), bbl, address, normalized, row.get("zipcode"),
             address_catalog_source),
        )
        premise_id = stable_id("premise", bbl, normalized)
        addressable_id = stable_id("addressable_unit", premise_id, normalized_unit)
        catalog.execute(
            "INSERT INTO premises(premise_id,bbl,address,normalized,zipcode,source,first_seen,last_seen) "
            "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(bbl,normalized) DO UPDATE SET last_seen=excluded.last_seen",
            (premise_id, bbl, address, normalized, row.get("zipcode"), address_catalog_source, stamp, stamp),
        )
        premise_id = catalog.execute(
            "SELECT premise_id FROM premises WHERE bbl=? AND normalized=?", (bbl, normalized)
        ).fetchone()[0]
        before = catalog.total_changes
        addressable_id = stable_id("addressable_unit", premise_id, normalized_unit)
        catalog.execute(
            "INSERT INTO addressable_units(addressable_unit_id,premise_id,unit_label,normalized_unit,first_seen,last_seen) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(premise_id,normalized_unit) DO UPDATE SET last_seen=excluded.last_seen",
            (addressable_id, premise_id, label, normalized_unit, stamp, stamp),
        )
        imported_addresses += int(catalog.total_changes > before)
        addressable_id = catalog.execute(
            "SELECT addressable_unit_id FROM addressable_units WHERE premise_id=? AND normalized_unit=?",
            (premise_id, normalized_unit),
        ).fetchone()[0]
        catalog.execute(
            "INSERT INTO observations(observation_id,document_id,source,source_ref,observed_at,observation_kind,"
            "address,unit_label,status,raw_fields,evidence_grade) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(source,source_ref,observed_at,observation_kind) DO UPDATE SET document_id=excluded.document_id,"
            "address=excluded.address,unit_label=excluded.unit_label,raw_fields=excluded.raw_fields",
            (observation_id, document_id, address_catalog_source, source_ref, observed_at,
             "official_unit_lot_address", address, label, "reported", payload, "source_document"),
        )
        for entity_type, entity_id, method, rationale in (
            ("building", bbl, "official_unit_lot_bbl", "DOF statement supplies the unit-lot BBL and address"),
            ("unit", unit_id, "official_unit_lot_bbl_and_designation", "DOF records supply the residential tax class and unit designation"),
            ("addressable_unit", addressable_id, "official_unit_lot_address_and_designation", "DOF records supply the unit-lot address and unit designation"),
        ):
            catalog.execute(
                "INSERT INTO entity_matches(observation_id,entity_type,entity_id,status,confidence,method,rationale,matched_at) "
                "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(observation_id,entity_type) DO UPDATE SET "
                "entity_id=excluded.entity_id,status=excluded.status,confidence=excluded.confidence,method=excluded.method,"
                "rationale=excluded.rationale,matched_at=excluded.matched_at",
                (observation_id, entity_type, entity_id, "resolved", 1.0, method, rationale, stamp),
            )

    catalog.commit()
    summary.update({
        "removed_nonresidential_units": removed_units,
        "removed_nonresidential_addressable_units": removed_addressable,
        "residential_units_inserted_or_updated": imported_units,
        "residential_addresses_inserted_or_updated": imported_addresses,
        "catalog_writes": 1,
    })
    Path(args.summary).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    catalog.close()


if __name__ == "__main__":
    main()
