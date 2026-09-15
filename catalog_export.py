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
        "SELECT u.unit_id, u.bbl, u.unit_label, u.normalized_unit, u.first_seen, u.last_seen "
        "FROM units u WHERE EXISTS ("
        "SELECT 1 FROM entity_matches m JOIN observations o ON o.observation_id=m.observation_id "
        "JOIN release_sources r ON r.source=o.source "
        "WHERE m.entity_type='unit' AND m.status='resolved' AND m.entity_id=u.unit_id"
        ") ORDER BY u.bbl, u.normalized_unit",
    ),
    "unit_observations.csv": (
        ("unit_id", "observation_id", "source", "source_ref", "observed_at",
         "observation_kind", "address", "unit_label", "bedrooms", "bathrooms", "price",
         "status", "evidence_grade", "resolution_confidence", "resolution_method", "matched_at"),
        "SELECT m.entity_id AS unit_id, o.observation_id, o.source, o.source_ref, o.observed_at, "
        "o.observation_kind, o.address, o.unit_label, o.bedrooms, o.bathrooms, o.price, o.status, "
        "o.evidence_grade, m.confidence AS resolution_confidence, m.method AS resolution_method, "
        "m.matched_at FROM entity_matches m JOIN observations o ON o.observation_id=m.observation_id "
        "JOIN release_sources r ON r.source=o.source "
        "WHERE m.entity_type='unit' AND m.status='resolved' AND m.entity_id IS NOT NULL "
        "ORDER BY m.entity_id, o.observed_at, o.observation_id",
    ),
    "sources.csv": (
        ("source", "source_kind", "methodology", "first_seen", "last_seen"),
        "SELECT s.source, s.source_kind, s.methodology, s.first_seen, s.last_seen "
        "FROM sources s JOIN release_sources r ON r.source=s.source "
        "WHERE EXISTS (SELECT 1 FROM observations o JOIN entity_matches m "
        "ON m.observation_id=o.observation_id WHERE o.source=s.source "
        "AND m.entity_type='unit' AND m.status='resolved' AND m.entity_id IS NOT NULL) "
        "ORDER BY s.source",
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


def _load_source_policy(path):
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        sys.exit(f"cannot read source policy {path}: {error}")
    if not isinstance(policy, dict) or not isinstance(policy.get("policy_id"), str):
        sys.exit(f"source policy must contain a string policy_id: {path}")
    sources = policy.get("included_sources")
    if not isinstance(sources, list) or not sources or not all(isinstance(value, str) for value in sources):
        sys.exit(f"source policy must contain a nonempty included_sources list: {path}")
    if len(sources) != len(set(sources)):
        sys.exit(f"source policy contains duplicate included_sources: {path}")
    return policy


def _install_release_sources(connection, sources):
    connection.execute("CREATE TEMP TABLE release_sources (source TEXT PRIMARY KEY)")
    connection.executemany("INSERT INTO release_sources(source) VALUES (?)", ((source,) for source in sources))


def main():
    parser = argparse.ArgumentParser(description="Export the stable Pricefixed catalog release format.")
    parser.add_argument("--db", required=True, help="completed catalog SQLite database")
    parser.add_argument("--out", required=True, help="new or empty output directory")
    parser.add_argument("--release-id", help="published snapshot identifier (default: output directory name)")
    parser.add_argument("--commit", help="Pricefixed source commit used to build this snapshot")
    parser.add_argument(
        "--source-policy",
        default=str(Path(__file__).with_name("release_sources.json")),
        help="JSON policy listing sources approved for the public snapshot",
    )
    args = parser.parse_args()

    database = Path(args.db)
    output = Path(args.out)
    if not database.is_file():
        sys.exit(f"catalog database not found: {database}")
    if output.exists() and any(output.iterdir()):
        sys.exit(f"output directory must be new or empty: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=output.parent))

    source_policy = _load_source_policy(Path(args.source_policy))
    connection = sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True)
    try:
        _install_release_sources(connection, source_policy["included_sources"])
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
            "source_policy": {
                "policy_id": source_policy["policy_id"],
                "file": "source-policy.json",
                "included_sources": len(source_policy["included_sources"]),
            },
            "excluded_counts": {
                "units_without_included_source_evidence": connection.execute("SELECT COUNT(*) FROM units").fetchone()[0]
                - files["units.csv"]["rows"],
            },
            "excluded_fields": ["source_documents.payload", "observations.raw_fields"],
        }
        policy_output = temporary / "source-policy.json"
        policy_output.write_text(json.dumps(source_policy, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest["source_policy"]["sha256"] = _sha256(policy_output)
        (temporary / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if output.exists():
            output.rmdir()
        temporary.rename(output)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
