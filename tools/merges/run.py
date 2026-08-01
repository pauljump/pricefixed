#!/usr/bin/env python3
"""Run the documented citywide coverage-growth merge sequence with explicit inputs."""
import argparse
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent


def _run(script, *args):
    command = [sys.executable, str(HERE / script), *map(str, args)]
    print("+", " ".join(command), flush=True)
    subprocess.run(command, check=True)


def main():
    parser = argparse.ArgumentParser(description="Run the Pricefixed citywide coverage-growth merge pass.")
    parser.add_argument("--catalog-db", required=True, help="catalog SQLite path to update")
    parser.add_argument("--work-dir", required=True, help="directory for extracted CSV and hierarchy SQLite")
    parser.add_argument("--streeteasy-db", required=True, help="archived StreetEasy SQLite path")
    parser.add_argument("--elliman-db", required=True, help="archived Elliman SQLite path")
    parser.add_argument("--corcoran-db", required=True, help="archived Corcoran SQLite path")
    parser.add_argument("--vayo-db", required=True, help="archived all_nyc_units SQLite path")
    args = parser.parse_args()

    work_dir = Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    extracted = work_dir / "extracted_addresses.csv"
    hierarchy = work_dir / "hierarchy.db"

    _run("extract_all.py", "--out", extracted, "--streeteasy-db", args.streeteasy_db,
         "--elliman-db", args.elliman_db, "--corcoran-db", args.corcoran_db,
         "--vayo-db", args.vayo_db)
    _run("build_hierarchy.py", "--catalog-db", args.catalog_db, "--raw-csv", extracted,
         "--out-db", hierarchy)
    _run("merge_known.py", "--hierarchy-db", hierarchy, "--catalog-db", args.catalog_db,
         "--vayo-db", args.vayo_db)
    _run("merge_single_family.py", "--catalog-db", args.catalog_db)
    _run("merge_tradable_tiebreak.py", "--hierarchy-db", hierarchy, "--catalog-db", args.catalog_db,
         "--vayo-db", args.vayo_db)
    _run("merge_condo_unit_lots.py", "--catalog-db", args.catalog_db)


if __name__ == "__main__":
    main()
