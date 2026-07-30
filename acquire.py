#!/usr/bin/env python3
"""Run bounded, resumable citywide catalog acquisition pages.

The catalog importers preserve each source row. This runner records only page-level
progress so a large source can be resumed after a network, machine, or storage break.
"""
import argparse
import sys

from pricefixed.catalog import Catalog, init_catalog_db
from pricefixed.catalog.core import _now
from pricefixed.record.core import parse_boro


SOURCES = {
    "hpd_violations": "import_hpd_violations",
    "hpd_omo_work_orders": "import_hpd_omo_work_orders",
    "acris_property_legals": "import_acris_property_legals",
    "acris_unit_legals": "import_acris_unit_legals",
    "condo_units": "import_condo_units",
    "evictions": "import_evictions",
    "hpd_registration_coverage": "import_hpd_registration_coverage",
    "annualized_sales": "import_annualized_sales",
    "rolling_sales": "import_rolling_sales",
    "dob_now_jobs": "import_dob_now_jobs",
    "dob_now_permits": "import_dob_now_permits",
    "hpd_problems": "import_hpd_problems",
}


def main():
    ap = argparse.ArgumentParser(description="Acquire catalog sources in durable pages.")
    ap.add_argument("--db", required=True, help="catalog SQLite path")
    ap.add_argument("--source", choices=tuple(SOURCES), required=True)
    ap.add_argument("--page-size", type=int, default=50000)
    ap.add_argument("--pages", type=int, default=1, help="pages to acquire this invocation")
    ap.add_argument("--offset", type=int, default=None,
                    help="explicit first page offset; later runs resume recorded progress")
    ap.add_argument("--keyset", action="store_true",
                    help="use durable source-specific keyset paging")
    ap.add_argument("--cursor", default=None,
                    help="bootstrap a keyset cursor when no durable cursor exists")
    ap.add_argument("--boro", default=None, help="MN/BX/BK/QN/SI; omit for citywide")
    args = ap.parse_args()
    if args.page_size <= 0 or args.pages <= 0:
        sys.exit("--page-size and --pages must be positive")
    try:
        boro = parse_boro(args.boro)
    except ValueError as exc:
        sys.exit(str(exc))
    scope = args.boro.upper() if args.boro else "citywide"
    catalog = Catalog(init_catalog_db(args.db))
    method = getattr(catalog, SOURCES[args.source])
    if args.keyset:
        if args.source not in ("hpd_problems", "acris_unit_legals") or args.offset is not None:
            sys.exit("--keyset is only valid for hpd_problems or acris_unit_legals without --offset")
        state = catalog.conn.execute(
            "SELECT cursor_date,cursor_ref FROM acquisition_keysets WHERE source=? AND scope=?",
            (args.source, scope),
        ).fetchone()
        cursor_date, cursor_ref = state if state else (None, None)
        if args.cursor:
            if state:
                sys.exit("--cursor cannot override an existing durable keyset cursor")
            cursor_ref = args.cursor
        for _ in range(args.pages):
            before = catalog.conn.execute("SELECT COUNT(*) FROM units").fetchone()[0]
            if args.source == "hpd_problems":
                stats = method(limit=args.page_size, boro=boro, before_date=cursor_date,
                               before_problem_id=cursor_ref)
                returned = stats["hpd_problem_rows"]
                next_date, next_ref = stats["hpd_problem_next_date"], stats["hpd_problem_next_id"]
            else:
                stats = method(limit=args.page_size, boro=boro, before_document_id=cursor_ref)
                returned = stats["acris_legal_rows"]
                next_date, next_ref = None, stats["acris_legal_next_document_id"]
            after = catalog.conn.execute("SELECT COUNT(*) FROM units").fetchone()[0]
            catalog.conn.execute(
                "INSERT OR REPLACE INTO acquisition_keysets "
                "(source,scope,cursor_date,cursor_ref,returned_rows,completed_at) VALUES (?,?,?,?,?,?)",
                (args.source, scope, next_date, next_ref, returned, _now()),
            )
            catalog.conn.commit()
            print("source=%s cursor=%s/%s rows=%d units=%d (+%d)" %
                  (args.source, next_date, next_ref, returned, after, after - before))
            if returned < args.page_size or not next_ref or (args.source == "hpd_problems" and not next_date):
                break
            cursor_date, cursor_ref = next_date, next_ref
        return
    if args.offset is None:
        terminal = catalog.conn.execute(
            "SELECT offset, returned_rows FROM acquisition_pages "
            "WHERE source=? AND scope=? AND returned_rows < requested_rows "
            "ORDER BY offset DESC LIMIT 1",
            (args.source, scope),
        ).fetchone()
        if terminal:
            print("source=%s terminal_offset=%d rows=%d; use --offset to begin a new refresh range" %
                  (args.source, terminal[0], terminal[1]))
            return
    row = catalog.conn.execute(
        "SELECT COALESCE(MAX(offset + requested_rows), 0) FROM acquisition_pages "
        "WHERE source=? AND scope=? AND returned_rows=requested_rows",
        (args.source, scope),
    ).fetchone()
    offset = args.offset if args.offset is not None else row[0]
    for _ in range(args.pages):
        before = catalog.conn.execute("SELECT COUNT(*) FROM units").fetchone()[0]
        started = _now()
        stats = method(limit=args.page_size, boro=boro, offset=offset)
        returned = stats[next(key for key in stats if key.endswith("_rows"))]
        after = catalog.conn.execute("SELECT COUNT(*) FROM units").fetchone()[0]
        catalog.conn.execute(
            "INSERT OR REPLACE INTO acquisition_pages "
            "(source,scope,offset,requested_rows,returned_rows,canonical_units_before,canonical_units_after,started_at,completed_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (args.source, scope, offset, args.page_size, returned, before, after, started,
             _now()),
        )
        catalog.conn.commit()
        print("source=%s offset=%d rows=%d units=%d (+%d)" %
              (args.source, offset, returned, after, after - before))
        if returned < args.page_size:
            break
        offset += args.page_size


if __name__ == "__main__":
    main()
