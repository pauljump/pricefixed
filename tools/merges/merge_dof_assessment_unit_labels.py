#!/usr/bin/env python3
"""Merge reviewed current DOF assessment apartment labels for official condo unit lots."""
import argparse
import csv
import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.engine.crosswalk import normalize_address
from pricefixed.engine.dedupe import normalize_unit
from tools.merges.mine_dof_assessment_unit_labels import RESIDENTIAL_TAX_CLASSES, usable_label

SOURCE = "dof_property_assessment_unit_labels"


def stable_id(prefix, *parts):
    material = "\x1f".join(str(part or "") for part in parts)
    return f"{prefix}_{hashlib.sha256(material.encode('utf-8')).hexdigest()[:20]}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--catalog-db", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with open(args.csv, newline="", encoding="utf-8") as handle:
        raw_rows = list(csv.DictReader(handle))
    catalog = sqlite3.connect(args.catalog_db)
    catalog.execute("PRAGMA busy_timeout=60000")
    candidates = {}
    rejected = 0
    for row in raw_rows:
        bbl = str(row.get("unit_lot_bbl") or "").strip()
        label = str(row.get("unit_label") or "").strip()
        normalized = usable_label(label)
        official = catalog.execute(
            "SELECT unit_designation FROM official_unit_lots WHERE unit_lot_bbl=?", (bbl,)
        ).fetchone()
        official_normalized = normalize_unit(official[0]) if official and official[0] else ""
        if (not official or row.get("tax_class") not in RESIDENTIAL_TAX_CLASSES or
                not normalized or normalized != row.get("normalized_unit") or
                (official_normalized and official_normalized != normalized) or
                row.get("basis") not in {"matches_condo_designation", "fills_blank_condo_designation"} or
                not row.get("source_ref") or not row.get("source_url")):
            rejected += 1
            continue
        candidates[(bbl, normalized)] = row
    net_new = sum(
        not catalog.execute("SELECT 1 FROM units WHERE bbl=? AND normalized_unit=?", key).fetchone()
        for key in candidates
    )
    summary = {
        "input_rows": len(raw_rows), "verified_unique_units": len(candidates),
        "net_new_units": net_new, "rejected_rows": rejected, "catalog_writes": 0,
    }
    if not args.apply:
        Path(args.summary).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2, sort_keys=True))
        catalog.close()
        return

    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    catalog.execute("PRAGMA journal_mode=WAL")
    catalog.execute("BEGIN")
    catalog.execute(
        "INSERT INTO sources(source,source_kind,methodology,first_seen,last_seen) VALUES (?,?,?,?,?) "
        "ON CONFLICT(source) DO UPDATE SET last_seen=excluded.last_seen",
        (SOURCE, "public_record",
         "Current final-period NYC DOF property assessment apartment label on an official residential condo unit-lot BBL; accepted only when it agrees with the condo registry or fills its blank designation",
         stamp, stamp),
    )
    for (bbl, normalized), row in candidates.items():
        label = row["unit_label"].strip()
        source_ref = row["source_ref"].strip()
        document_id = stable_id("doc", SOURCE, source_ref)
        observation_id = stable_id("obs", SOURCE, source_ref, "official_assessment_unit_label")
        unit_id = stable_id("unit", bbl, normalized)
        address = str(row.get("address") or "").strip()
        payload = json.dumps({
            "unit_lot_bbl": bbl, "unit_label": label, "address": address,
            "tax_class": row.get("tax_class", ""), "building_class": row.get("building_class", ""),
            "assessment_year": row.get("assessment_year", ""),
            "assessment_period": row.get("assessment_period", ""),
            "source_url": row["source_url"], "basis": row.get("basis", ""),
        }, sort_keys=True)
        catalog.execute(
            "INSERT OR IGNORE INTO source_documents(document_id,source,source_ref,retrieved_at,payload,payload_kind) "
            "VALUES (?,?,?,?,?,?)",
            (document_id, SOURCE, source_ref, stamp, payload, "selected_public_assessment_fields"),
        )
        catalog.execute(
            "INSERT INTO buildings(bbl,source,first_seen,last_seen) VALUES (?,?,?,?) "
            "ON CONFLICT(bbl) DO UPDATE SET last_seen=excluded.last_seen", (bbl, SOURCE, stamp, stamp),
        )
        catalog.execute(
            "INSERT INTO units(unit_id,bbl,unit_label,normalized_unit,first_seen,last_seen) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(bbl,normalized_unit) DO UPDATE SET last_seen=excluded.last_seen",
            (unit_id, bbl, label, normalized, stamp, stamp),
        )
        unit_id = catalog.execute(
            "SELECT unit_id FROM units WHERE bbl=? AND normalized_unit=?", (bbl, normalized)
        ).fetchone()[0]
        normalized_address = normalize_address(address)
        addressable_id = None
        if normalized_address:
            catalog.execute(
                "INSERT INTO addresses(address_id,bbl,address,normalized,zipcode,source) VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(bbl,normalized) DO UPDATE SET address=excluded.address",
                (stable_id("addr", bbl, normalized_address), bbl, address, normalized_address, None, SOURCE),
            )
            premise_id = stable_id("premise", bbl, normalized_address)
            catalog.execute(
                "INSERT INTO premises(premise_id,bbl,address,normalized,zipcode,source,first_seen,last_seen) "
                "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(bbl,normalized) DO UPDATE SET last_seen=excluded.last_seen",
                (premise_id, bbl, address, normalized_address, None, SOURCE, stamp, stamp),
            )
            premise_id = catalog.execute(
                "SELECT premise_id FROM premises WHERE bbl=? AND normalized=?", (bbl, normalized_address)
            ).fetchone()[0]
            addressable_id = stable_id("addressable_unit", premise_id, normalized)
            catalog.execute(
                "INSERT INTO addressable_units(addressable_unit_id,premise_id,unit_label,normalized_unit,first_seen,last_seen) "
                "VALUES (?,?,?,?,?,?) ON CONFLICT(premise_id,normalized_unit) DO UPDATE SET last_seen=excluded.last_seen",
                (addressable_id, premise_id, label, normalized, stamp, stamp),
            )
            addressable_id = catalog.execute(
                "SELECT addressable_unit_id FROM addressable_units WHERE premise_id=? AND normalized_unit=?",
                (premise_id, normalized),
            ).fetchone()[0]
        observed_at = str(row.get("observed_at") or stamp[:10])
        catalog.execute(
            "INSERT INTO observations(observation_id,document_id,source,source_ref,observed_at,observation_kind,"
            "address,unit_label,status,raw_fields,evidence_grade) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(source,source_ref,observed_at,observation_kind) DO UPDATE SET raw_fields=excluded.raw_fields",
            (observation_id, document_id, SOURCE, source_ref, observed_at,
             "official_assessment_unit_label", address or None, label, "reported", payload, "source_document"),
        )
        for entity_type, entity_id in (("building", bbl), ("unit", unit_id), ("addressable_unit", addressable_id)):
            if not entity_id:
                continue
            catalog.execute(
                "INSERT INTO entity_matches(observation_id,entity_type,entity_id,status,confidence,method,rationale,matched_at) "
                "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(observation_id,entity_type) DO UPDATE SET "
                "entity_id=excluded.entity_id,status=excluded.status,confidence=excluded.confidence,"
                "method=excluded.method,rationale=excluded.rationale,matched_at=excluded.matched_at",
                (observation_id, entity_type, entity_id, "resolved", 1.0,
                 "official_assessment_unit_lot_and_label",
                 "DOF assessment supplies a residential unit-lot BBL and apartment label", stamp),
            )
    catalog.commit()
    summary["catalog_writes"] = 1
    Path(args.summary).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    catalog.close()


if __name__ == "__main__":
    main()
