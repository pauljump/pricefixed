#!/usr/bin/env python3
"""Resume resolution of the downloaded ACRIS unit-evidence queue.

This runner keeps the source stage and catalog paths explicit, works in bounded
batches, and stops before local disk space becomes dangerously low.
"""
import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.catalog import Catalog, init_catalog_db


def _pending(stage_db):
    import sqlite3

    connection = sqlite3.connect(f"file:{Path(stage_db).resolve()}?mode=ro", uri=True)
    try:
        return connection.execute(
            "SELECT COUNT(*) FROM staged_acris_unit_legals WHERE resolved_at IS NULL"
        ).fetchone()[0]
    finally:
        connection.close()


def _emit(log, payload):
    line = json.dumps(payload, sort_keys=True)
    print(line, flush=True)
    if log:
        with log.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def main():
    parser = argparse.ArgumentParser(description="Resume the staged ACRIS unit-evidence backlog.")
    parser.add_argument("--catalog-db", required=True, help="catalog SQLite database to update")
    parser.add_argument("--stage-db", required=True, help="downloaded ACRIS staging database")
    parser.add_argument("--batch-size", type=int, default=1000, help="rows per catalog transaction")
    parser.add_argument("--max-batches", type=int, default=1, help="batches to run; 0 means until empty")
    parser.add_argument("--min-free-gb", type=float, default=8.0, help="stop below this free-space threshold")
    parser.add_argument("--log", type=Path, help="append JSON progress records to this file")
    parser.add_argument("--dry-run", action="store_true", help="report the queue without changing either database")
    args = parser.parse_args()

    catalog_db = Path(args.catalog_db)
    stage_db = Path(args.stage_db)
    if not catalog_db.is_file():
        sys.exit(f"catalog database not found: {catalog_db}")
    if not stage_db.is_file():
        sys.exit(f"ACRIS stage database not found: {stage_db}")
    if args.batch_size <= 0:
        sys.exit("--batch-size must be positive")
    if args.max_batches < 0:
        sys.exit("--max-batches cannot be negative")
    if args.min_free_gb <= 0:
        sys.exit("--min-free-gb must be positive")

    pending = _pending(stage_db)
    start = {
        "event": "start",
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "pending": pending,
        "batch_size": args.batch_size,
        "max_batches": args.max_batches,
        "dry_run": args.dry_run,
    }
    _emit(args.log, start)
    if args.dry_run or pending == 0:
        return

    connection = init_catalog_db(catalog_db)
    catalog = Catalog(connection)
    batches = 0
    try:
        while pending and (args.max_batches == 0 or batches < args.max_batches):
            free_gb = shutil.disk_usage(catalog_db.parent).free / (1024 ** 3)
            if free_gb < args.min_free_gb:
                _emit(args.log, {"event": "stop", "reason": "low_disk", "free_gb": round(free_gb, 2)})
                return
            stats = catalog.import_staged_acris_unit_legals(stage_db, limit=args.batch_size)
            batches += 1
            pending = stats["acris_stage_rows_remaining"]
            _emit(args.log, {
                "event": "batch",
                "batch": batches,
                "free_gb": round(free_gb, 2),
                "pending": pending,
                "stats": stats,
            })
            if stats["acris_stage_rows"] == 0:
                break
    finally:
        connection.close()
    _emit(args.log, {"event": "complete", "batches": batches, "pending": pending})


if __name__ == "__main__":
    main()
