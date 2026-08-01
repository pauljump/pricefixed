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
    counts = {
        "buildings": _optional_count(connection, "buildings"),
        "addresses": _optional_count(connection, "addresses"),
        "units": _optional_count(connection, "units"),
        "observations": _optional_count(connection, "observations"),
        "resolved_unit_observations": _scalar(
            connection,
            "SELECT COUNT(*) FROM entity_matches "
            "WHERE entity_type='unit' AND status='resolved' AND entity_id IS NOT NULL",
        ),
        "unresolved_unit_observations": _scalar(
            connection,
            "SELECT COUNT(*) FROM entity_matches "
            "WHERE entity_type='unit' AND status!='resolved'",
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
        "counts": counts,
        "coverage": coverage,
        "sources": _grouped(
            connection,
            "SELECT source, COUNT(*) FROM observations GROUP BY source ORDER BY COUNT(*) DESC, source",
        ),
        "evidence_grades": _grouped(
            connection,
            "SELECT evidence_grade, COUNT(*) FROM observations "
            "GROUP BY evidence_grade ORDER BY COUNT(*) DESC, evidence_grade",
        ),
        "unit_resolution_methods": _grouped(
            connection,
            "SELECT method, COUNT(*) FROM entity_matches "
            "WHERE entity_type='unit' GROUP BY method ORDER BY COUNT(*) DESC, method",
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
    args = parser.parse_args()

    database = Path(args.db)
    output = Path(args.out)
    if not database.is_file():
        sys.exit(f"catalog database not found: {database}")
    if output.exists() and output.is_dir():
        sys.exit(f"output path is a directory: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True)
    try:
        report = build_report(connection, database.name, release_id=args.release_id, commit=args.commit)
    finally:
        connection.close()
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
