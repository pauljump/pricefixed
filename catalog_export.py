#!/usr/bin/env python3
"""Create the stable, payload-free Pricefixed catalog release bundle.

    python3 catalog_export.py --db /path/to/catalog.db --out pricefixed-catalog-YYYY-MM-DD
"""
import argparse
import csv
import hashlib
import json
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


EXPORTS = {
    "units.csv": (
        ("unit_id", "bbl", "unit_label", "normalized_unit", "first_seen", "last_seen"),
        "SELECT unit_id, bbl, unit_label, normalized_unit, first_seen, last_seen "
        "FROM units ORDER BY bbl, normalized_unit",
    ),
    "unit_observations.csv": (
        ("unit_id", "observation_id", "source", "source_ref", "observed_at",
         "observation_kind", "address", "unit_label", "bedrooms", "bathrooms", "price",
         "status", "evidence_grade", "resolution_confidence", "resolution_method", "matched_at"),
        "SELECT m.entity_id AS unit_id, o.observation_id, o.source, o.source_ref, o.observed_at, "
        "o.observation_kind, o.address, o.unit_label, o.bedrooms, o.bathrooms, o.price, o.status, "
        "o.evidence_grade, m.confidence AS resolution_confidence, m.method AS resolution_method, "
        "m.matched_at FROM entity_matches m JOIN observations o ON o.observation_id=m.observation_id "
        "WHERE m.entity_type='unit' AND m.status='resolved' AND m.entity_id IS NOT NULL "
        "ORDER BY m.entity_id, o.observed_at, o.observation_id",
    ),
    "sources.csv": (
        ("source", "source_kind", "methodology", "first_seen", "last_seen"),
        "SELECT source, source_kind, methodology, first_seen, last_seen FROM sources ORDER BY source",
    ),
}


def _write_csv(connection, path, columns, query):
    count = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for row in connection.execute(query):
            writer.writerow(row)
            count += 1
    return count


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description="Export the stable Pricefixed catalog release format.")
    parser.add_argument("--db", required=True, help="completed catalog SQLite database")
    parser.add_argument("--out", required=True, help="new or empty output directory")
    parser.add_argument("--release-id", help="published snapshot identifier (default: output directory name)")
    parser.add_argument("--commit", help="Pricefixed source commit used to build this snapshot")
    args = parser.parse_args()

    database = Path(args.db)
    output = Path(args.out)
    if not database.is_file():
        sys.exit(f"catalog database not found: {database}")
    if output.exists() and any(output.iterdir()):
        sys.exit(f"output directory must be new or empty: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=output.parent))

    connection = sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True)
    try:
        files = {}
        for name, (columns, query) in EXPORTS.items():
            path = temporary / name
            files[name] = {"rows": _write_csv(connection, path, columns, query), "sha256": _sha256(path)}
        manifest = {
            "format": "pricefixed-catalog-v1",
            "release_id": args.release_id or output.name,
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "source_database": database.name,
            "software_commit": args.commit,
            "files": files,
            "excluded_fields": ["source_documents.payload", "observations.raw_fields"],
        }
        (temporary / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if output.exists():
            output.rmdir()
        temporary.rename(output)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
