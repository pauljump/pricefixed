#!/usr/bin/env python3
"""Build the evidence-backed NYC housing catalog from pricefixed's source databases.

    python3 catalog.py --record record.db --listings listings.db
    python3 catalog.py --status

The output is `catalog.db` by default. It never overwrites source facts: it imports
them as observations and records its own entity-resolution claims separately.
"""
import argparse
import os
import sys

from pricefixed.catalog import Catalog, init_catalog_db


def _print_status(stats):
    for key, value in stats.items():
        print(f"  {key:30} {value}")


def _print_coverage(rows, limit):
    grouped = {}
    for row in rows:
        summary = grouped.setdefault(row["source"], {"listings": 0, "resolved": 0})
        summary["listings"] += row["listings"]
        summary["resolved"] += row["resolved"]
    print("  active listing coverage by source:")
    for source, summary in sorted(grouped.items(), key=lambda item: item[1]["listings"], reverse=True):
        rate = summary["resolved"] / summary["listings"] if summary["listings"] else 0
        print(f"    {source:16} {summary['resolved']:5}/{summary['listings']:<5} {rate:6.1%}")
    print(f"\n  active listing coverage by ZIP (top {limit} by inventory):")
    for row in rows[:limit]:
        print(f"    {row['zipcode']:8} {row['source']:16} "
              f"{row['resolved']:5}/{row['listings']:<5} {row['resolution_rate']:6.1%}")


def main():
    ap = argparse.ArgumentParser(description="Build pricefixed's canonical housing catalog.")
    ap.add_argument("--db", default="catalog.db", help="catalog SQLite path (default: ./catalog.db)")
    ap.add_argument("--record", default="record.db", help="building-record SQLite path")
    ap.add_argument("--listings", default="listings.db", help="listing-source SQLite path")
    ap.add_argument("--source", choices=("base", "listings", "derive_addressable_units", "hpd_violations", "hpd_problems", "nycha_hmc_violations", "ose_str_snapshot", "hpd_omo_work_orders", "acris_property_legals", "acris_unit_legals", "acris_stage", "vayo_all_nyc_units", "vayo_streeteasy_unit_summary", "vayo_elliman_mls_archive", "vayo_corcoran_archive", "annualized_sales", "rolling_sales", "evictions", "dob_now_jobs", "dob_now_permits", "hpd_registration_coverage", "condo_units", "pad_addresses", "pad_listing_zips", "all"), default="base",
                    help="base imports record/listings dbs; listings refreshes source snapshots only")
    ap.add_argument("--limit", type=int, default=None,
                    help="cap rows from a direct source; use for a sample import")
    ap.add_argument("--offset", type=int, default=0,
                    help="start a paged direct-source import at this Socrata row offset")
    ap.add_argument("--boro", default=None,
                    help="scope a direct source to MN/BX/BK/QN/SI or borough code 1-5")
    ap.add_argument("--zips", default=None,
                    help="comma-separated ZIP codes required by the PAD address source")
    ap.add_argument("--all-addresses", action="store_true",
                    help="import all NYC PAD addresses; only valid with --source pad_addresses")
    ap.add_argument("--snapshot", default=None, help="published source snapshot path (required by ose_str_snapshot)")
    ap.add_argument("--snapshot-date", default=None, help="publication date YYYY-MM-DD for a snapshot import")
    ap.add_argument("--stage-db", default=None, help="raw-source staging database (required by acris_stage)")
    ap.add_argument("--vayo-db", default=None, help="archived Vayo all_nyc_units.db (required by vayo_all_nyc_units)")
    ap.add_argument("--cursor", default=None, help="source-specific durable keyset cursor")
    ap.add_argument("--status", action="store_true", help="show catalog counts and exit")
    ap.add_argument("--no-status", action="store_true",
                    help="skip the expensive final aggregate status after an import")
    ap.add_argument("--coverage", action="store_true",
                    help="show active scraped-listing resolution coverage by source and ZIP")
    ap.add_argument("--gaps", action="store_true",
                    help="show largest PLUTO residential-capacity gaps without naming missing units")
    ap.add_argument("--reconcile-candidates", action="store_true",
                    help="resolve ambiguous listings only with unique official unit corroboration")
    ap.add_argument("--demote-vayo-text-mined", action="store_true",
                    help="retain but demote Vayo rows explicitly marked text-mined")
    ap.add_argument("--materialize-capacity-slots", action="store_true",
                    help="materialize anonymous PLUTO-counted capacity slots; never named apartments")
    ap.add_argument("--slot-batches", type=int, default=1,
                    help="bounded building batches for --materialize-capacity-slots (default: 1)")
    ap.add_argument("--derive-batches", type=int, default=1,
                    help="observation batches for --source derive_addressable_units (default: 1)")
    ap.add_argument("--coverage-limit", type=int, default=25,
                    help="ZIP rows to show with --coverage (default: 25)")
    args = ap.parse_args()

    conn = init_catalog_db(args.db)
    catalog = Catalog(conn)
    if args.status:
        _print_status(catalog.status())
        return
    if args.coverage:
        if not os.path.exists(args.listings):
            sys.exit(f"listings database not found: {args.listings}")
        _print_coverage(catalog.listing_coverage(args.listings), args.coverage_limit)
        return
    if args.gaps:
        from pricefixed.record.core import parse_boro
        try:
            boro = parse_boro(args.boro)
        except ValueError as exc:
            sys.exit(f"  {exc}")
        for row in catalog.capacity_gaps(args.coverage_limit, boro):
            print("  {borough:13} {bbl} {units_res:5} capacity {named_units:5} named {unnamed_capacity:5} gap  {address}".format(**row))
        return
    if args.reconcile_candidates:
        _print_status(catalog.reconcile_unit_candidates())
        return
    if args.demote_vayo_text_mined:
        _print_status(catalog.demote_vayo_text_mined_units())
        return
    if args.materialize_capacity_slots:
        _print_status(catalog.materialize_capacity_slots(batches=args.slot_batches))
        return

    if args.source in ("base", "all"):
        if not os.path.exists(args.record):
            sys.exit(f"record database not found: {args.record}")
        if not os.path.exists(args.listings):
            sys.exit(f"listings database not found: {args.listings}")
        buildings = catalog.import_record_db(args.record)
        listing_stats = catalog.import_listings_db(args.listings)
        print(f"  imported {buildings} building records")
        _print_status(listing_stats)
    if args.source == "listings":
        if not os.path.exists(args.listings):
            sys.exit(f"listings database not found: {args.listings}")
        _print_status(catalog.import_listings_db(args.listings))
    if args.source == "derive_addressable_units":
        _print_status(catalog.derive_addressable_units(
            limit=args.limit or 10000, batches=args.derive_batches
        ))
    if args.source == "vayo_all_nyc_units":
        if not args.vayo_db:
            sys.exit("vayo_all_nyc_units requires --vayo-db PATH")
        _print_status(catalog.import_vayo_all_nyc_units(
            args.vayo_db, limit=args.limit or 10000, after_unit_id=args.cursor
        ))
    if args.source == "vayo_streeteasy_unit_summary":
        if not args.vayo_db:
            sys.exit("vayo_streeteasy_unit_summary requires --vayo-db PATH")
        _print_status(catalog.import_vayo_streeteasy_unit_summary(
            args.vayo_db, limit=args.limit or 10000, after_id=args.cursor
        ))
    if args.source == "vayo_elliman_mls_archive":
        if not args.vayo_db:
            sys.exit("vayo_elliman_mls_archive requires --vayo-db PATH")
        _print_status(catalog.import_vayo_elliman_mls_archive(
            args.vayo_db, limit=args.limit or 10000, after_listing_id=args.cursor
        ))
    if args.source == "vayo_corcoran_archive":
        if not args.vayo_db:
            sys.exit("vayo_corcoran_archive requires --vayo-db PATH")
        _print_status(catalog.import_vayo_corcoran_archive(
            args.vayo_db, limit=args.limit or 10000, after_listing_id=args.cursor
        ))
    if args.source in ("hpd_violations", "all"):
        from pricefixed.record.core import parse_boro
        try:
            boro = parse_boro(args.boro)
        except ValueError as exc:
            sys.exit(f"  {exc}")
        _print_status(catalog.import_hpd_violations(limit=args.limit, boro=boro, offset=args.offset))
    if args.source == "hpd_problems":
        from pricefixed.record.core import parse_boro
        try:
            boro = parse_boro(args.boro)
        except ValueError as exc:
            sys.exit(f"  {exc}")
        _print_status(catalog.import_hpd_problems(limit=args.limit, boro=boro, offset=args.offset))
    if args.source == "nycha_hmc_violations":
        from pricefixed.record.core import parse_boro
        try:
            boro = parse_boro(args.boro)
        except ValueError as exc:
            sys.exit(f"  {exc}")
        _print_status(catalog.import_nycha_hmc_violations(limit=args.limit, boro=boro))
    if args.source == "ose_str_snapshot":
        if not args.snapshot or not args.snapshot_date:
            sys.exit("ose_str_snapshot requires --snapshot PATH and --snapshot-date YYYY-MM-DD")
        _print_status(catalog.import_ose_str_snapshot(args.snapshot, args.snapshot_date))
    if args.source in ("hpd_omo_work_orders", "all"):
        from pricefixed.record.core import parse_boro
        try:
            boro = parse_boro(args.boro)
        except ValueError as exc:
            sys.exit(f"  {exc}")
        _print_status(catalog.import_hpd_omo_work_orders(limit=args.limit, boro=boro, offset=args.offset))
    if args.source in ("acris_property_legals", "all"):
        from pricefixed.record.core import parse_boro
        try:
            boro = parse_boro(args.boro)
        except ValueError as exc:
            sys.exit(f"  {exc}")
        _print_status(catalog.import_acris_property_legals(limit=args.limit, boro=boro, offset=args.offset))
    if args.source == "acris_unit_legals":
        from pricefixed.record.core import parse_boro
        try:
            boro = parse_boro(args.boro)
        except ValueError as exc:
            sys.exit(f"  {exc}")
        _print_status(catalog.import_acris_unit_legals(limit=args.limit, boro=boro, offset=args.offset))
    if args.source == "acris_stage":
        if not args.stage_db:
            sys.exit("acris_stage requires --stage-db PATH")
        _print_status(catalog.import_staged_acris_unit_legals(args.stage_db, limit=args.limit or 1000))
    if args.source in ("annualized_sales", "all"):
        from pricefixed.record.core import parse_boro
        try:
            boro = parse_boro(args.boro)
        except ValueError as exc:
            sys.exit(f"  {exc}")
        _print_status(catalog.import_annualized_sales(limit=args.limit, boro=boro, offset=args.offset))
    if args.source == "rolling_sales":
        from pricefixed.record.core import parse_boro
        try:
            boro = parse_boro(args.boro)
        except ValueError as exc:
            sys.exit(f"  {exc}")
        _print_status(catalog.import_rolling_sales(limit=args.limit, boro=boro, offset=args.offset))
    if args.source in ("evictions", "all"):
        from pricefixed.record.core import parse_boro
        try:
            boro = parse_boro(args.boro)
        except ValueError as exc:
            sys.exit(f"  {exc}")
        _print_status(catalog.import_evictions(limit=args.limit, boro=boro, offset=args.offset))
    if args.source in ("dob_now_jobs", "all"):
        from pricefixed.record.core import parse_boro
        try:
            boro = parse_boro(args.boro)
        except ValueError as exc:
            sys.exit(f"  {exc}")
        _print_status(catalog.import_dob_now_jobs(limit=args.limit, boro=boro, offset=args.offset))
    if args.source == "dob_now_permits":
        from pricefixed.record.core import parse_boro
        try:
            boro = parse_boro(args.boro)
        except ValueError as exc:
            sys.exit(f"  {exc}")
        _print_status(catalog.import_dob_now_permits(limit=args.limit, boro=boro, offset=args.offset))
    if args.source == "hpd_registration_coverage":
        from pricefixed.record.core import parse_boro
        try:
            boro = parse_boro(args.boro)
        except ValueError as exc:
            sys.exit(f"  {exc}")
        _print_status(catalog.import_hpd_registration_coverage(limit=args.limit, boro=boro, offset=args.offset))
    if args.source in ("condo_units", "all"):
        _print_status(catalog.import_condo_units(limit=args.limit, offset=args.offset))
    if args.source == "pad_addresses":
        if args.all_addresses and args.zips:
            sys.exit("PAD import accepts either --zips or --all-addresses, not both")
        if not args.zips and not args.all_addresses:
            sys.exit("PAD import requires --zips or --all-addresses")
        zips = [zipcode.strip() for zipcode in args.zips.split(",")] if args.zips else None
        try:
            _print_status(catalog.import_pad_addresses(zips, limit=args.limit))
        except ValueError as exc:
            sys.exit(f"  {exc}")
    if args.source == "pad_listing_zips":
        if not os.path.exists(args.listings):
            sys.exit(f"listings database not found: {args.listings}")
        zips = catalog.listing_zipcodes(args.listings)
        _print_status(catalog.import_pad_addresses(zips, limit=args.limit))
    if not args.no_status:
        print("\n  catalog status:")
        _print_status(catalog.status())


if __name__ == "__main__":
    main()
