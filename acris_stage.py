#!/usr/bin/env python3
"""Stage official ACRIS unit-labeled legal rows before catalog resolution.

The full ACRIS unit-label universe is millions of rows. Staging keeps immutable
primary-source payloads and a durable keyset cursor in a compact SQLite database;
the heavier catalog entity-resolution pass can then run independently and resume.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone

from pricefixed.record.core import socrata


DATASET = "8h5j-fqxa"
SELECT = (
    "document_id,borough,block,lot,property_type,street_number,street_name,unit,good_through_date"
)
SOURCE = "acris_unit_legals"


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _row_id(payload):
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def init_stage_db(path):
    conn = sqlite3.connect(path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS staged_acris_unit_legals (
            row_id          TEXT PRIMARY KEY,
            document_id     TEXT NOT NULL,
            raw_payload     TEXT NOT NULL,
            retrieved_at    TEXT NOT NULL,
            resolved_at     TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_staged_acris_document
            ON staged_acris_unit_legals(document_id);
        CREATE INDEX IF NOT EXISTS idx_staged_acris_unresolved
            ON staged_acris_unit_legals(resolved_at, document_id);
        CREATE TABLE IF NOT EXISTS stage_keysets (
            source          TEXT PRIMARY KEY,
            cursor_ref      TEXT,
            returned_rows   INTEGER NOT NULL,
            completed_at    TEXT NOT NULL
        );
        """
    )
    conn.commit()
    return conn


def fetch_page(cursor_ref, page_size):
    where = "unit IS NOT NULL AND unit <> ''"
    if cursor_ref:
        cursor = str(cursor_ref).replace("'", "''")
        # Include the document boundary again; row IDs make that idempotent.
        where += f" AND document_id <= '{cursor}'"
    return socrata(DATASET, select=SELECT, where=where, order="document_id DESC", limit=page_size)


def stage_page(conn, page_size, cursor=None):
    state = conn.execute(
        "SELECT cursor_ref FROM stage_keysets WHERE source=?", (SOURCE,)
    ).fetchone()
    if state and cursor is not None:
        raise ValueError("a durable cursor already exists; do not override it")
    cursor_ref = state[0] if state else cursor
    rows = fetch_page(cursor_ref, page_size)
    retrieved_at = _now()
    prepared = []
    for row in rows:
        document_id = str(row.get("document_id") or "")
        if not document_id:
            continue
        payload = json.dumps(row, default=str, sort_keys=True, separators=(",", ":"))
        prepared.append((_row_id(payload), document_id, payload, retrieved_at))
    before = conn.total_changes
    conn.executemany(
        "INSERT OR IGNORE INTO staged_acris_unit_legals (row_id,document_id,raw_payload,retrieved_at) "
        "VALUES (?,?,?,?)",
        prepared,
    )
    inserted = conn.total_changes - before
    next_cursor = min((str(row["document_id"]) for row in rows if row.get("document_id")), default=None)
    conn.execute(
        "INSERT OR REPLACE INTO stage_keysets (source,cursor_ref,returned_rows,completed_at) VALUES (?,?,?,?)",
        (SOURCE, next_cursor, len(rows), _now()),
    )
    conn.commit()
    return {"rows": len(rows), "inserted": inserted, "cursor": next_cursor}


def main():
    ap = argparse.ArgumentParser(description="Stage official ACRIS unit-label rows with a durable keyset.")
    ap.add_argument("--db", required=True, help="staging SQLite path")
    ap.add_argument("--page-size", type=int, default=10000)
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("--cursor", default=None, help="initial document ID cursor only")
    args = ap.parse_args()
    if args.page_size <= 0 or args.pages <= 0:
        sys.exit("--page-size and --pages must be positive")
    conn = init_stage_db(args.db)
    try:
        for page in range(args.pages):
            stats = stage_page(conn, args.page_size, args.cursor if page == 0 else None)
            print("rows=%d inserted=%d cursor=%s" % (stats["rows"], stats["inserted"], stats["cursor"]))
            if stats["rows"] < args.page_size or not stats["cursor"]:
                break
    finally:
        conn.close()


if __name__ == "__main__":
    main()
