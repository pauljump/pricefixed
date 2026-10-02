#!/usr/bin/env python3
"""Merge cross-checked residential CONDO_AREA unit-lot deltas into the catalog."""
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
from tools.merges.mine_condo_area_delta import official_unit_label


SOURCE = "nyc_dof_condo_area_units"


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
        rows = list(csv.DictReader(handle))
    catalog = sqlite3.connect(args.catalog_db)
    catalog.execute("PRAGMA busy_timeout=60000")
    candidates = {}
    rejected = 0
    for row in rows:
        bbl = str(row.get("unit_lot_bbl") or "").strip()
        base = str(row.get("condo_base_bbl") or "").strip()
        label = str(row.get("unit_label") or "").strip()
        normalized = official_unit_label(label)
        valid_basis = row.get("basis") in {
            "matching_condo_area_and_acris_labels", "residential_geometry_plus_acris_label",
            "condo_area_designation",
        }
        if (len(bbl) != 10 or len(base) != 10 or not normalized or
                normalized != row.get("normalized_unit") or not valid_basis or
                "b5bf-t8kd" not in row.get("source_url", "") or
                "8h5j-fqxa" not in row.get("acris_source_url", "")):
            rejected += 1
            continue
        if catalog.execute("SELECT 1 FROM official_unit_lots WHERE unit_lot_bbl=?", (bbl,)).fetchone():
            rejected += 1
            continue
        if catalog.execute(
            "SELECT 1 FROM official_unit_lots WHERE condo_base_bbl=? AND "
            "REPLACE(REPLACE(UPPER(COALESCE(unit_designation,'')),'-',''),' ','')=?",
            (base, normalized),
        ).fetchone():
            rejected += 1
            continue
        candidates[(bbl, normalized)] = row
    summary = {
        "input_rows": len(rows), "verified_unique_units": len(candidates),
        "net_new_units": sum(not catalog.execute(
            "SELECT 1 FROM units WHERE bbl=? AND normalized_unit=?", key
        ).fetchone() for key in candidates),
        "rejected_rows": rejected, "catalog_writes": 0,
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
        "INSERT INTO sources VALUES (?,?,?,?,?) ON CONFLICT(source) DO UPDATE SET last_seen=excluded.last_seen",
        (SOURCE, "public_record",
         "NYC DOF CONDO_AREA unit geometry, accepted only when absent from the weekly condo registry and independently supported by ACRIS or a unique explicit dwelling designation",
         stamp, stamp),
    )
    for (bbl, normalized), row in candidates.items():
        label = row["unit_label"].strip()
        source_ref = row["object_id"].strip()
        document_id = stable_id("doc", SOURCE, source_ref)
        observation_id = stable_id("obs", SOURCE, source_ref, "official_condo_area_unit")
        unit_id = stable_id("unit", bbl, normalized)
        address = str(row.get("address") or "").strip().upper()
        payload = json.dumps(row, sort_keys=True)
        catalog.execute(
            "INSERT OR IGNORE INTO source_documents VALUES (?,?,?,?,?,?)",
            (document_id, SOURCE, source_ref, stamp, payload, "selected_public_condo_area_fields"),
        )
        catalog.execute(
            "INSERT INTO buildings(bbl,source,first_seen,last_seen) VALUES (?,?,?,?) "
            "ON CONFLICT(bbl) DO UPDATE SET last_seen=excluded.last_seen",
            (bbl, SOURCE, stamp, stamp),
        )
        catalog.execute(
            "INSERT INTO units VALUES (?,?,?,?,?,?) ON CONFLICT(bbl,normalized_unit) DO UPDATE SET last_seen=excluded.last_seen",
            (unit_id, bbl, label, normalized, stamp, stamp),
        )
        unit_id = catalog.execute(
            "SELECT unit_id FROM units WHERE bbl=? AND normalized_unit=?", (bbl, normalized)
        ).fetchone()[0]
        catalog.execute(
            "INSERT INTO official_unit_lots "
            "(unit_lot_bbl,condo_base_bbl,condo_key,unit_designation,floor_text,model,source,source_ref,document_id,record_status,first_seen,last_seen,raw_fields) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (bbl, row["condo_base_bbl"], row.get("condo_key"), label, row.get("floor_text"),
             row.get("model"), SOURCE, source_ref, document_id, "reported", stamp, stamp, payload),
        )
        catalog.execute(
            "INSERT INTO official_unit_lot_links VALUES (?,?,?,?,?,?,?)",
            (bbl, unit_id, "resolved", 1.0, "cross_checked_official_unit_lot",
             "CONDO_AREA unit BBL and ACRIS/designation evidence identify one residential unit", stamp),
        )
        addressable_id = None
        normalized_address = normalize_address(address)
        if normalized_address:
            catalog.execute(
                "INSERT INTO addresses VALUES (?,?,?,?,?,?) ON CONFLICT(bbl,normalized) DO UPDATE SET address=excluded.address",
                (stable_id("addr", bbl, normalized_address), bbl, address, normalized_address, None, SOURCE),
            )
            premise_id = stable_id("premise", bbl, normalized_address)
            catalog.execute(
                "INSERT INTO premises VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(bbl,normalized) DO UPDATE SET last_seen=excluded.last_seen",
                (premise_id, bbl, address, normalized_address, None, SOURCE, stamp, stamp),
            )
            premise_id = catalog.execute(
                "SELECT premise_id FROM premises WHERE bbl=? AND normalized=?", (bbl, normalized_address)
            ).fetchone()[0]
            addressable_id = stable_id("addressable_unit", premise_id, normalized)
            catalog.execute(
                "INSERT INTO addressable_units VALUES (?,?,?,?,?,?) ON CONFLICT(premise_id,normalized_unit) DO UPDATE SET last_seen=excluded.last_seen",
                (addressable_id, premise_id, label, normalized, stamp, stamp),
            )
            addressable_id = catalog.execute(
                "SELECT addressable_unit_id FROM addressable_units WHERE premise_id=? AND normalized_unit=?",
                (premise_id, normalized),
            ).fetchone()[0]
        observed_at = row.get("observed_at") or stamp[:10]
        catalog.execute(
            "INSERT INTO observations(observation_id,document_id,source,source_ref,observed_at,observation_kind,address,unit_label,status,raw_fields,evidence_grade) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (observation_id, document_id, SOURCE, source_ref, observed_at, "official_condo_area_unit",
             address or None, label, "reported", payload, "corroborated_public_records"),
        )
        for entity_type, entity_id, method in (
            ("building", bbl, "official_condo_area_unit_bbl"),
            ("unit", unit_id, "cross_checked_official_unit_lot_and_label"),
            ("addressable_unit", addressable_id, "acris_address_and_unit_label"),
        ):
            if entity_id:
                catalog.execute(
                    "INSERT INTO entity_matches VALUES (?,?,?,?,?,?,?,?)",
                    (observation_id, entity_type, entity_id, "resolved", 1.0, method,
                     "CONDO_AREA and ACRIS/designation evidence agree on the residential identity", stamp),
                )
    catalog.commit()
    summary["catalog_writes"] = 1
    Path(args.summary).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    catalog.close()


if __name__ == "__main__":
    main()
