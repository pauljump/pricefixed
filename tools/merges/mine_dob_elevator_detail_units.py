#!/usr/bin/env python3
"""Collect apartment labels from DOB elevator details with an official address bridge."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.engine.crosswalk import normalize_address
from pricefixed.engine.unit_mentions import extract_explicit_unit_labels


DATASET = "juyv-2jek"
API = f"https://data.cityofnewyork.us/resource/{DATASET}.json"
WHERE = (
    "job_filing_number is not null AND (upper(device_job_description) like '%APT %' OR "
    "upper(device_job_description) like '%APT.%' OR "
    "upper(device_job_description) like '%APT#%' OR "
    "upper(device_job_description) like '%APARTMENT%')"
)


def query(offset, limit):
    fields = "job_filing_number,device_id,physical_address,device_job_description"
    params = urlencode({
        "$select": fields, "$where": WHERE, "$order": "job_filing_number,device_id",
        "$limit": limit, "$offset": offset,
    })
    request = Request(f"{API}?{params}", headers={"User-Agent": "pricefixed-public-records/1.0"})
    with urlopen(request, timeout=180) as response:
        return json.loads(response.read())


def resolve_pad_bbl(catalog, address):
    normalized = normalize_address(address)
    if not normalized:
        return ""
    rows = catalog.execute(
        "SELECT DISTINCT bbl FROM addresses WHERE normalized=? AND source='nyc_pad'",
        (normalized,),
    ).fetchall()
    return rows[0][0] if len(rows) == 1 else ""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--catalog-db", required=True)
    parser.add_argument("--batch-size", type=int, default=25000)
    parser.add_argument("--pages", type=int)
    args = parser.parse_args()
    if args.batch_size <= 0 or (args.pages is not None and args.pages <= 0):
        sys.exit("--batch-size and --pages must be positive")
    connection = sqlite3.connect(args.db)
    connection.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS descriptions (
            job_filing_number TEXT PRIMARY KEY, bbl TEXT, address TEXT, zipcode TEXT,
            description TEXT NOT NULL, filing_date TEXT, extracted_labels TEXT NOT NULL,
            status TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS progress (
            source TEXT PRIMARY KEY, offset INTEGER NOT NULL, complete INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)
    catalog = sqlite3.connect(f"file:{Path(args.catalog_db).resolve()}?mode=ro", uri=True)
    source = "dob_elevator_detail_descriptions"
    state = connection.execute(
        "SELECT offset,complete FROM progress WHERE source=?", (source,)
    ).fetchone()
    offset = state[0] if state else 0
    if state and state[1]:
        print("DOB elevator-detail mining already complete")
        catalog.close()
        connection.close()
        return
    pages = 0
    while True:
        rows = query(offset, args.batch_size)
        output = []
        for row in rows:
            description = str(row.get("device_job_description") or "").strip()
            labels = extract_explicit_unit_labels(description)
            address = str(row.get("physical_address") or "").strip().upper()
            bbl = resolve_pad_bbl(catalog, address)
            source_ref = str(row.get("device_id") or "").strip()
            if not source_ref:
                continue
            status = "explicit_candidate" if bbl and labels else (
                "unresolved_address" if labels and not bbl else "ambiguous_unit_word"
            )
            output.append((
                source_ref, bbl, address, "", description, "", json.dumps(labels), status,
            ))
        connection.executemany(
            "INSERT OR REPLACE INTO descriptions "
            "(job_filing_number,bbl,address,zipcode,description,filing_date,extracted_labels,status) "
            "VALUES (?,?,?,?,?,?,?,?)", output,
        )
        offset += len(rows)
        complete = int(len(rows) < args.batch_size)
        connection.execute(
            "INSERT INTO progress(source,offset,complete,updated_at) VALUES (?,?,?,datetime('now')) "
            "ON CONFLICT(source) DO UPDATE SET offset=excluded.offset,complete=excluded.complete,updated_at=excluded.updated_at",
            (source, offset, complete),
        )
        connection.commit()
        explicit = connection.execute(
            "SELECT COUNT(*) FROM descriptions WHERE status='explicit_candidate'"
        ).fetchone()[0]
        print(f"offset={offset} explicit_candidates={explicit}", flush=True)
        if complete:
            break
        pages += 1
        if args.pages is not None and pages >= args.pages:
            break
    catalog.close()
    connection.close()


if __name__ == "__main__":
    main()
