#!/usr/bin/env python3
"""
pricefixed record layer — build a canonical record of every NYC apartment building
and its public history, pulled fresh from NYC Open Data into a local SQLite file.

    python build_record.py                       # pull every source
    python build_record.py --source pluto
    python build_record.py --source pluto --limit 500   # sample instead of all of NYC
    python build_record.py --list                # show available sources
    python build_record.py --status              # counts in the current db
    python build_record.py --db mine.db          # write somewhere else (default: ./record.db)

The output is a plain SQLite database (tables: buildings, building_events,
record_source_log). Point Codex / Claude at it and build whatever you want.

NYC-wide these datasets are millions of rows — use --limit to sample.
"""
import argparse
import sys

from pricefixed.record import RECORD_SOURCES, init_record_db
from pricefixed.record.core import parse_boro


def main():
    ap = argparse.ArgumentParser(description="Build the NYC building public-record db.")
    ap.add_argument("--source", help="pull only this source (default: all)")
    ap.add_argument("--db", default="record.db", help="output SQLite path (default: record.db)")
    ap.add_argument("--limit", type=int, default=None,
                    help="cap rows fetched per source (sample instead of all of NYC)")
    ap.add_argument("--boro", default=None,
                    help="scope every source to one borough (MN/BX/BK/QN/SI or 1-5) so a "
                         "COMPLETE record — owners AND violations AND evictions — lands on "
                         "the same buildings, instead of a thin all-NYC sample that never overlaps")
    ap.add_argument("--list", action="store_true", help="list available sources and exit")
    ap.add_argument("--status", action="store_true", help="show counts and exit")
    ap.add_argument("--crosswalk", action="store_true",
                    help="build the address->BBL crosswalk from PLUTO and run the live "
                         "listing->BBL->building-facts join demo (see pricefixed/engine)")
    ap.add_argument("--portfolios", action="store_true",
                    help="cluster buildings into landlord portfolios by shared HPD "
                         "business address (Who-Owns-What) and print the top landlords")
    args = ap.parse_args()

    # Fail fast on a bad --boro before any network work (clean CLI error, not a traceback).
    try:
        boro = parse_boro(args.boro)
    except ValueError as e:
        sys.exit(f"  {e}")

    if args.list:
        for name, cls in sorted(RECORD_SOURCES.items()):
            print(f"  {name:18} {cls.description}")
        return

    if args.crosswalk:
        # The join keystone: normalize listing + PLUTO addresses to the same string,
        # look up which BBL an address belongs to, and attach a live listing to its
        # building's public record. See pricefixed/engine/crosswalk.py.
        from pricefixed.engine.crosswalk import _self_test, _demo
        print("normalize_address self-tests:")
        _self_test()
        _demo(db_record=args.db)
        return

    if args.portfolios:
        # Who-Owns-What: cluster single-purpose LLCs sharing an HPD business address
        # into landlord portfolios and roll up their combined accountability record.
        # See pricefixed/engine/portfolios.py.
        from pricefixed.engine.portfolios import _demo
        _demo(db_path=args.db)
        return

    conn = init_record_db(args.db)

    if args.status:
        print("  buildings by source-log:")
        for name, n in conn.execute(
            "SELECT source, SUM(rows) FROM record_source_log GROUP BY source ORDER BY 2 DESC"
        ):
            print(f"    {name:18} {n} rows pulled")
        bld = conn.execute("SELECT COUNT(*) FROM buildings").fetchone()[0]
        ev = conn.execute("SELECT COUNT(*) FROM building_events").fetchone()[0]
        print(f"  {'buildings':20} {bld}")
        print(f"  {'building_events':20} {ev}")
        for etype, n in conn.execute(
            "SELECT event_type, COUNT(*) FROM building_events GROUP BY event_type ORDER BY 2 DESC"
        ):
            print(f"    events[{etype}]      {n}")
        return

    if args.source:
        if args.source not in RECORD_SOURCES:
            sys.exit(f"unknown source '{args.source}'. try --list")
        sources = [args.source]
    else:
        sources = list(RECORD_SOURCES)

    if boro:
        from pricefixed.record.core import BOROUGHS
        print(f"  scope: {BOROUGHS[boro][1]} only (borough {boro})")

    grand = 0
    for name in sources:
        try:
            grand += RECORD_SOURCES[name]().run(conn, limit=args.limit, boro=boro)
        except Exception as e:  # noqa: BLE001 — one broken source shouldn't kill the run
            print(f"  {name}: FAILED — {e}")
    bld = conn.execute("SELECT COUNT(*) FROM buildings").fetchone()[0]
    ev = conn.execute("SELECT COUNT(*) FROM building_events").fetchone()[0]
    print(f"\ndone. {bld} buildings, {ev} events in {args.db} ({grand} rows this run)")


if __name__ == "__main__":
    main()
