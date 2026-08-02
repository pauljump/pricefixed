#!/usr/bin/env python3
"""Mine public NYC DOF statements for address labels on condo unit BBLs.

This stores only the public property address and source URL in the export. It
does not retain owner names, balances, or the downloaded tax-bill PDFs.
"""
import argparse
import csv
import re
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen


ADDRESS_RE = re.compile(r"^Property address:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE)


def fetch(row, statement_date):
    unit_lot_bbl, designation = row
    url = (
        "https://a836-edms.nyc.gov/dctm-rest/repositories/dofedmspts/StatementSearch"
        f"?bbl={unit_lot_bbl}&stmtDate={statement_date}&stmtType=SOA"
    )
    try:
        request = Request(url, headers={"User-Agent": "pricefixed-public-records/1.0"})
        with urlopen(request, timeout=30) as response:
            pdf = response.read()
        text = subprocess.run(
            ["pdftotext", "-", "-"], input=pdf, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, check=True,
        ).stdout.decode("utf-8", errors="replace")
        match = ADDRESS_RE.search(text)
        return {
            "unit_lot_bbl": unit_lot_bbl,
            "unit_designation": designation,
            "address": match.group(1).strip() if match else "",
            "source_url": url,
            "statement_date": statement_date,
            "status": "address_found" if match else "no_address_in_statement",
        }
    except Exception as exc:  # keep the queue resumable when one BBL fails
        return {
            "unit_lot_bbl": unit_lot_bbl,
            "unit_designation": designation,
            "address": "",
            "source_url": url,
            "statement_date": statement_date,
            "status": f"error:{type(exc).__name__}",
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-db", required=True)
    parser.add_argument("--condo-base-bbl", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--statement-date", default="20251115")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.workers <= 0:
        sys.exit("--workers must be positive")

    out = Path(args.out)
    completed = set()
    if out.exists():
        with out.open(encoding="utf-8", newline="") as handle:
            completed = {row["unit_lot_bbl"] for row in csv.DictReader(handle)}

    conn = sqlite3.connect(f"file:{Path(args.catalog_db).resolve()}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT unit_lot_bbl,unit_designation FROM official_unit_lots "
            "WHERE condo_base_bbl=? AND unit_lot_bbl NOT IN (SELECT bbl FROM addresses) "
            "ORDER BY unit_lot_bbl",
            (args.condo_base_bbl,),
        ).fetchall()
    finally:
        conn.close()
    rows = [row for row in rows if row[0] not in completed]
    out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ("unit_lot_bbl", "unit_designation", "address", "source_url", "statement_date", "status")
    write_header = not out.exists() or out.stat().st_size == 0
    with out.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(fetch, row, args.statement_date) for row in rows]
            for index, future in enumerate(as_completed(futures), 1):
                writer.writerow(future.result())
                if index % 100 == 0:
                    handle.flush()
                    print(f"completed {index}/{len(rows)}", flush=True)
                time.sleep(0.02)
    print(f"wrote {len(rows)} new results to {out}")


if __name__ == "__main__":
    main()
