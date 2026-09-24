#!/usr/bin/env python3
"""Create a small JSON quality report for a Pricefixed catalog database.

    python3 catalog_report.py --db /path/to/catalog.db --out quality-report.json
"""
import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from catalog_export import _install_release_sources, _load_source_policy


TARGET_HOUSING_UNITS = 3_705_000


def _scalar(connection, query, parameters=()):
    return connection.execute(query, parameters).fetchone()[0]


def _grouped(connection, query):
    return [{"value": value, "rows": rows} for value, rows in connection.execute(query)]


def _table_exists(connection, name):
    return bool(
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
    )


def _optional_count(connection, table):
    if not _table_exists(connection, table):
        return None
    return _scalar(connection, f"SELECT COUNT(*) FROM {table}")


def build_report(connection, database_name, release_id=None, commit=None):
    release_units = _scalar(
        connection,
        "SELECT COUNT(DISTINCT m.entity_id) FROM entity_matches m "
        "JOIN observations o ON o.observation_id=m.observation_id "
        "JOIN release_sources r ON r.source=o.source "
        "WHERE m.entity_type='unit' AND m.status='resolved' AND m.entity_id IS NOT NULL",
    )
    release_observations = _scalar(
        connection,
        "SELECT COUNT(*) FROM entity_matches m "
        "JOIN observations o ON o.observation_id=m.observation_id "
        "JOIN release_sources r ON r.source=o.source "
        "WHERE m.entity_type='unit' AND m.status='resolved' AND m.entity_id IS NOT NULL",
    )
    local_units = _optional_count(connection, "units") or 0
    counts = {
        "buildings": _optional_count(connection, "buildings"),
        "addresses": _optional_count(connection, "addresses"),
        "units": release_units,
        "observations": release_observations,
        "resolved_unit_observations": release_observations,
        "unresolved_unit_observations": _scalar(
            connection,
            "SELECT COUNT(*) FROM entity_matches m "
            "JOIN observations o ON o.observation_id=m.observation_id "
            "JOIN release_sources r ON r.source=o.source "
            "WHERE m.entity_type='unit' AND m.status!='resolved'",
        ),
        "official_unit_lots": _optional_count(connection, "official_unit_lots"),
        "anonymous_capacity_slots": _optional_count(connection, "housing_capacity_slots"),
    }
    units = counts["units"] or 0
    coverage = {
        "housing_stock_target": TARGET_HOUSING_UNITS,
        "identified_unit_ratio": round(units / TARGET_HOUSING_UNITS, 6),
    }

    report = {
        "format": "pricefixed-quality-report-v1",
        "release_id": release_id,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_database": database_name,
        "software_commit": commit,
        "count_scope": {
            "units": "records exported under source_policy",
            "observations": "resolved unit observations exported under source_policy",
            "buildings": "full local catalog context",
            "addresses": "full local catalog context",
            "official_unit_lots": "full local catalog context",
            "anonymous_capacity_slots": "full local catalog context",
        },
        "local_catalog_counts": {
            "units": local_units,
            "units_withheld_by_source_policy": local_units - release_units,
        },
        "counts": counts,
        "coverage": coverage,
        "sources": _grouped(
            connection,
            "SELECT o.source, COUNT(*) FROM observations o "
            "JOIN release_sources r ON r.source=o.source "
            "JOIN entity_matches m ON m.observation_id=o.observation_id "
            "WHERE m.entity_type='unit' AND m.status='resolved' AND m.entity_id IS NOT NULL "
            "GROUP BY o.source ORDER BY COUNT(*) DESC, o.source",
        ),
        "evidence_grades": _grouped(
            connection,
            "SELECT o.evidence_grade, COUNT(*) FROM observations o "
            "JOIN release_sources r ON r.source=o.source "
            "JOIN entity_matches m ON m.observation_id=o.observation_id "
            "WHERE m.entity_type='unit' AND m.status='resolved' AND m.entity_id IS NOT NULL "
            "GROUP BY o.evidence_grade ORDER BY COUNT(*) DESC, o.evidence_grade",
        ),
        "unit_resolution_methods": _grouped(
            connection,
            "SELECT m.method, COUNT(*) FROM entity_matches m "
            "JOIN observations o ON o.observation_id=m.observation_id "
            "JOIN release_sources r ON r.source=o.source "
            "WHERE m.entity_type='unit' AND m.status='resolved' AND m.entity_id IS NOT NULL "
            "GROUP BY m.method ORDER BY COUNT(*) DESC, m.method",
        ),
        "open_gaps": [],
        "warnings": [],
    }

    if counts["anonymous_capacity_slots"]:
        report["open_gaps"].append({
            "name": "anonymous_capacity_slots",
            "rows": counts["anonymous_capacity_slots"],
            "note": "These are source-reported housing counts, not named apartment records.",
        })
    if counts["unresolved_unit_observations"]:
        report["open_gaps"].append({
            "name": "unresolved_unit_observations",
            "rows": counts["unresolved_unit_observations"],
            "note": "These source rows were kept but not cleanly matched to a unit.",
        })
    if report["local_catalog_counts"]["units_withheld_by_source_policy"]:
        report["open_gaps"].append({
            "name": "units_withheld_by_source_policy",
            "rows": report["local_catalog_counts"]["units_withheld_by_source_policy"],
            "note": "These local unit identities have no supporting observation from a release-approved source.",
        })
    if not release_id:
        report["warnings"].append("release_id was not supplied")
    if not commit:
        report["warnings"].append("software_commit was not supplied")
    if counts["units"] == 0:
        report["warnings"].append("catalog has zero identified units")

    return report


def main():
    parser = argparse.ArgumentParser(description="Write a Pricefixed catalog quality report.")
    parser.add_argument("--db", required=True, help="completed catalog SQLite database")
    parser.add_argument("--out", required=True, help="JSON report path")
    parser.add_argument("--release-id", help="published snapshot identifier")
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
    if output.exists() and output.is_dir():
        sys.exit(f"output path is a directory: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    source_policy = _load_source_policy(Path(args.source_policy))
    connection = sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True)
    try:
        _install_release_sources(connection, source_policy["included_sources"])
        report = build_report(connection, database.name, release_id=args.release_id, commit=args.commit)
        report["source_policy"] = {
            "policy_id": source_policy["policy_id"],
            "included_sources": len(source_policy["included_sources"]),
        }
    finally:
        connection.close()
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
