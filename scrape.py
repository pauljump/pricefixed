#!/usr/bin/env python3
"""
pricefixed — pull apartment listings from landlord-direct sources into a local SQLite file.

    python scrape.py                 # pull every source
    python scrape.py --source nooklyn
    python scrape.py --list          # show available sources
    python scrape.py --status        # counts in the current db
    python scrape.py --db mine.db    # write somewhere else (default: ./listings.db)

The output is a plain SQLite database (tables: listings, price_history, pull_log).
Point Codex / Claude at it and build whatever you want.
"""
import argparse
import sys

from pricefixed.core import init_db
from pricefixed.adapters import ADAPTERS


def main():
    ap = argparse.ArgumentParser(description="Pull apartment listings into SQLite.")
    ap.add_argument("--source", help="pull only this source (default: all)")
    ap.add_argument("--db", default="listings.db", help="output SQLite path (default: listings.db)")
    ap.add_argument("--list", action="store_true", help="list available sources and exit")
    ap.add_argument("--status", action="store_true", help="show counts and exit")
    ap.add_argument("--dedupe", action="store_true",
                    help="collapse listings into distinct physical units across sources "
                         "(writes the unit_dedup table + canonical_listings view) and exit")
    args = ap.parse_args()

    if args.list:
        for name, cls in sorted(ADAPTERS.items()):
            print(f"  {name:16} {cls.description}")
        return

    conn = init_db(args.db)

    if args.status:
        for name, n in conn.execute(
            "SELECT source, COUNT(*) FROM listings WHERE status='active' GROUP BY source ORDER BY 2 DESC"
        ):
            print(f"  {name:16} {n} active")
        total = conn.execute("SELECT COUNT(*) FROM listings WHERE status='active'").fetchone()[0]
        print(f"  {'TOTAL':16} {total} active")
        return

    if args.dedupe:
        # Entity-resolution: the same physical unit can surface in more than one feed
        # (a landlord-direct listing also carried by the broker marketplace). Collapse
        # them to one canonical row per unit. See pricefixed/engine/dedupe.py.
        from pricefixed.engine.dedupe import build_units
        stats = build_units(conn)
        print(f"dedupe: {stats['raw_listings']} listings -> {stats['distinct_units']} units "
              f"({stats['duplicate_units']} with 2+ listings mapped)")
        return

    if args.source:
        if args.source not in ADAPTERS:
            sys.exit(f"unknown source '{args.source}'. try --list")
        sources = [args.source]
    else:
        sources = list(ADAPTERS)

    grand_new = grand_total = 0
    for name in sources:
        try:
            new, _ = ADAPTERS[name]().run(conn)
            grand_new += new
        except Exception as e:  # noqa: BLE001 — one broken source shouldn't kill the run
            print(f"  {name}: FAILED — {e}")
    grand_total = conn.execute("SELECT COUNT(*) FROM listings WHERE status='active'").fetchone()[0]
    print(f"\ndone. {grand_total} active listings in {args.db} ({grand_new} new this run)")


if __name__ == "__main__":
    main()
