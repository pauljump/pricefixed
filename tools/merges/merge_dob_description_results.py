#!/usr/bin/env python3
"""Merge deterministically verified local-model DOB description labels."""
import argparse
import csv
import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.catalog.core import NON_DWELLING_UNIT_LABELS
from pricefixed.engine.crosswalk import normalize_address
from pricefixed.engine.dedupe import normalize_unit


def stable_id(prefix, *parts):
    value = "\x1f".join(str(part or "") for part in parts)
    return f"{prefix}_{hashlib.sha256(value.encode()).hexdigest()[:20]}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--catalog-db", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--source", default="dob_now_job_description_units")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with open(args.csv, newline="", encoding="utf-8") as handle:
        raw_rows = list(csv.DictReader(handle))
    candidates = {}
    rejected = 0
    for row in raw_rows:
        bbl = str(row.get("bbl") or "").strip()
        label = str(row.get("unit_label") or "").strip()
        normalized = normalize_unit(label)
        if (len(bbl) != 10 or bbl[0] not in "12345" or not normalized or
                label.upper() in NON_DWELLING_UNIT_LABELS or not row.get("source_url") or
                not row.get("source_ref") or not row.get("evidence")):
            rejected += 1
            continue
        candidates[(bbl, normalized)] = (row, normalized)

    catalog = sqlite3.connect(args.catalog_db)
    catalog.execute("PRAGMA busy_timeout=60000")
    net_new = sum(
        not catalog.execute("SELECT 1 FROM units WHERE bbl=? AND normalized_unit=?", key).fetchone()
        for key in candidates
    )
    summary = {
        "input_rows": len(raw_rows), "verified_unique_units": len(candidates),
        "net_new_units": net_new, "rejected_rows": rejected, "catalog_writes": 0,
    }
    if not args.apply:
        Path(args.summary).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        catalog.close()
        return

    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    catalog.execute(
        "INSERT INTO sources(source,source_kind,methodology,first_seen,last_seen) VALUES (?,?,?,?,?) "
        "ON CONFLICT(source) DO UPDATE SET last_seen=excluded.last_seen",
        (args.source, "public_record",
         "Explicit apartment label in an official DOB job description; extracted by deterministic regex, "
         "reviewed by the documented local Qwen model, and accepted only when its evidence is verbatim source text",
         stamp, stamp),
    )
    for (bbl, normalized), (row, _normalized) in candidates.items():
        label = row["unit_label"].strip()
        upstream_ref = row["source_ref"].strip()
        source_ref = stable_id("dob_description", upstream_ref, normalized)
        document_id = stable_id("doc", args.source, source_ref)
        observation_id = stable_id("obs", args.source, source_ref, "official_unit_label")
        unit_id = stable_id("unit", bbl, normalized)
        payload = json.dumps({
            "upstream_source_ref": upstream_ref, "source_url": row["source_url"],
            "bbl": bbl, "address": row.get("address", ""), "unit_label": label,
            "evidence": row["evidence"], "local_model_confidence": row.get("confidence", ""),
        }, sort_keys=True)
        catalog.execute(
            "INSERT OR IGNORE INTO source_documents(document_id,source,source_ref,retrieved_at,payload,payload_kind) "
            "VALUES (?,?,?,?,?,?)",
            (document_id, args.source, source_ref, stamp, payload, "verified_nyc_open_data_fields"),
        )
        catalog.execute(
            "INSERT INTO buildings(bbl,source,first_seen,last_seen) VALUES (?,?,?,?) "
            "ON CONFLICT(bbl) DO UPDATE SET last_seen=excluded.last_seen",
            (bbl, args.source, stamp, stamp),
        )
        catalog.execute(
            "INSERT INTO units(unit_id,bbl,unit_label,normalized_unit,first_seen,last_seen) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(bbl,normalized_unit) DO UPDATE SET last_seen=excluded.last_seen",
            (unit_id, bbl, label, normalized, stamp, stamp),
        )
        unit_id = catalog.execute(
            "SELECT unit_id FROM units WHERE bbl=? AND normalized_unit=?", (bbl, normalized)
        ).fetchone()[0]
        address = row.get("address", "")
        normalized_address = normalize_address(address)
        addressable_id = None
        if normalized_address:
            catalog.execute(
                "INSERT INTO addresses(address_id,bbl,address,normalized,zipcode,source) VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(bbl,normalized) DO UPDATE SET address=excluded.address",
                (stable_id("addr", bbl, normalized_address), bbl, address, normalized_address, None, args.source),
            )
            premise_id = stable_id("premise", bbl, normalized_address)
            catalog.execute(
                "INSERT INTO premises(premise_id,bbl,address,normalized,zipcode,source,first_seen,last_seen) "
                "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(bbl,normalized) DO UPDATE SET last_seen=excluded.last_seen",
                (premise_id, bbl, address, normalized_address, None, args.source, stamp, stamp),
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
            (observation_id, document_id, args.source, source_ref, observed_at, "official_unit_label",
             address or None, label, "reported", payload, "source_document"),
        )
        for entity_type, entity_id in (("building", bbl), ("unit", unit_id),
                                       ("addressable_unit", addressable_id)):
            if not entity_id:
                continue
            catalog.execute(
                "INSERT INTO entity_matches(observation_id,entity_type,entity_id,status,confidence,method,rationale,matched_at) "
                "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(observation_id,entity_type) DO UPDATE SET "
                "entity_id=excluded.entity_id,status=excluded.status,confidence=excluded.confidence",
                (observation_id, entity_type, entity_id, "resolved", 1.0,
                 "official_bbl_and_verified_description_label",
                 "DOB supplies the BBL and verbatim apartment-label evidence", stamp),
            )
    catalog.commit()
    summary["catalog_writes"] = 1
    Path(args.summary).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    catalog.close()


if __name__ == "__main__":
    main()
