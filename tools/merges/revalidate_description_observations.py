#!/usr/bin/env python3
"""Remove description observations no longer reproduced by their source parser."""
import argparse
import json
import sqlite3
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.engine.dedupe import normalize_unit
from pricefixed.engine.unit_mentions import extract_explicit_unit_labels
from tools.merges.mine_dob_electrical_detail_units import extract_electrical_detail_labels


def load_packets(paths, packet_id_prefix=""):
    packets = {}
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                packet = json.loads(line)
                source_ref = str(
                    packet.get("source_ref")
                    or str(packet["id"]).removeprefix(packet_id_prefix)
                )
                if source_ref in packets and packets[source_ref]["text"] != packet["text"]:
                    raise ValueError(f"conflicting packet text for source ref {source_ref}")
                packets[source_ref] = packet
    return packets


def observation_audit(catalog, source, packets, extractor):
    invalid = []
    missing = []
    rows = catalog.execute(
        "SELECT observation_id,document_id,unit_label,raw_fields FROM observations WHERE source=?",
        (source,),
    ).fetchall()
    for observation_id, document_id, label, raw_fields in rows:
        try:
            payload = json.loads(raw_fields or "{}")
        except json.JSONDecodeError:
            payload = {}
        source_ref = str(payload.get("upstream_source_ref") or "")
        packet = packets.get(source_ref)
        if not packet:
            missing.append(observation_id)
            continue
        reproduced = {normalize_unit(value) for value in extractor(packet["text"])}
        if normalize_unit(label) not in reproduced:
            invalid.append((observation_id, document_id))
    return rows, invalid, missing


def linked_entities(catalog, observation_ids, entity_type):
    entities = set()
    for observation_id in observation_ids:
        row = catalog.execute(
            "SELECT entity_id FROM entity_matches WHERE observation_id=? AND entity_type=?",
            (observation_id, entity_type),
        ).fetchone()
        if row and row[0]:
            entities.add(row[0])
    return entities


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packets", action="append", required=True)
    parser.add_argument("--catalog-db", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--packet-id-prefix", default="")
    parser.add_argument(
        "--source-parser", choices=("default", "electrical_detail"), default="default"
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    packets = load_packets(args.packets, args.packet_id_prefix)
    extractor = (
        extract_electrical_detail_labels
        if args.source_parser == "electrical_detail" else extract_explicit_unit_labels
    )
    catalog = sqlite3.connect(args.catalog_db)
    catalog.execute("PRAGMA busy_timeout=60000")
    rows, invalid, missing = observation_audit(catalog, args.source, packets, extractor)
    if missing:
        raise SystemExit(
            f"cannot revalidate {len(missing)} observations without their source packets"
        )
    invalid_ids = [row[0] for row in invalid]
    unit_ids = linked_entities(catalog, invalid_ids, "unit")
    addressable_ids = linked_entities(catalog, invalid_ids, "addressable_unit")
    summary = {
        "source": args.source,
        "source_observations": len(rows),
        "invalid_observations": len(invalid),
        "missing_packets": 0,
        "linked_units_reviewed": len(unit_ids),
        "linked_addressable_units_reviewed": len(addressable_ids),
        "observations_removed": 0,
        "orphan_units_removed": 0,
        "orphan_addressable_units_removed": 0,
        "catalog_writes": 0,
    }
    if args.apply:
        catalog.execute("BEGIN IMMEDIATE")
        for observation_id in invalid_ids:
            catalog.execute("DELETE FROM entity_matches WHERE observation_id=?", (observation_id,))
            catalog.execute("DELETE FROM observations WHERE observation_id=?", (observation_id,))
        for _, document_id in invalid:
            if document_id:
                catalog.execute(
                    "DELETE FROM source_documents WHERE document_id=? AND NOT EXISTS "
                    "(SELECT 1 FROM observations WHERE document_id=?)",
                    (document_id, document_id),
                )
        removed_addressable = 0
        for entity_id in addressable_ids:
            before = catalog.total_changes
            catalog.execute(
                "DELETE FROM addressable_units WHERE addressable_unit_id=? AND NOT EXISTS "
                "(SELECT 1 FROM entity_matches WHERE entity_type='addressable_unit' AND entity_id=?)",
                (entity_id, entity_id),
            )
            removed_addressable += int(catalog.total_changes > before)
        removed_units = 0
        for entity_id in unit_ids:
            before = catalog.total_changes
            catalog.execute(
                "DELETE FROM units WHERE unit_id=? AND NOT EXISTS "
                "(SELECT 1 FROM entity_matches WHERE entity_type='unit' AND entity_id=?) AND NOT EXISTS "
                "(SELECT 1 FROM official_unit_lot_links WHERE unit_id=?)",
                (entity_id, entity_id, entity_id),
            )
            removed_units += int(catalog.total_changes > before)
        catalog.commit()
        summary.update({
            "observations_removed": len(invalid),
            "orphan_units_removed": removed_units,
            "orphan_addressable_units_removed": removed_addressable,
            "catalog_writes": 1,
        })
    Path(args.summary).write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    catalog.close()


if __name__ == "__main__":
    main()
