#!/usr/bin/env python3
"""Collect explicit apartment labels from official DOB-issued OATH cases."""
import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.engine.unit_mentions import extract_explicit_unit_labels


DATASET = "jz4z-kudi"
API = f"https://data.cityofnewyork.us/resource/{DATASET}.json"
TEXT_FILTER = (
    "(upper(violation_description) like '%APT%' OR "
    "upper(violation_description) like '%APARTMENT%' OR "
    "upper(violation_details) like '%APT%' OR "
    "upper(violation_details) like '%APARTMENT%')"
)
WHERE = f"issuing_agency='DEPT. OF BUILDINGS' AND {TEXT_FILTER}"
BOROUGH = {
    "MANHATTAN": "1", "BRONX": "2", "BROOKLYN": "3", "QUEENS": "4",
    "STATEN IS": "5", "STATEN ISLAND": "5",
}


def make_bbl(borough, block, lot):
    boro = BOROUGH.get(str(borough or "").strip().upper(), "")
    block = "".join(char for char in str(block or "") if char.isdigit())
    lot = "".join(char for char in str(lot or "") if char.isdigit())
    if not boro or not block or not lot:
        return ""
    return boro + block.zfill(5)[-5:] + lot.zfill(4)[-4:]


def query(offset, limit):
    fields = (
        "ticket_number,issuing_agency,violation_date,violation_location_borough,"
        "violation_location_house,violation_location_street_name,violation_location_zip_code,"
        "violation_location_block_no,violation_location_lot_no,violation_description,violation_details"
    )
    params = urlencode({
        "$select": fields, "$where": WHERE, "$order": "ticket_number",
        "$limit": limit, "$offset": offset,
    })
    request = Request(f"{API}?{params}", headers={"User-Agent": "pricefixed-public-records/1.0"})
    with urlopen(request, timeout=180) as response:
        return json.loads(response.read())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--batch-size", type=int, default=25000)
    parser.add_argument("--pages", type=int, help="Bound this run; rerun without it to resume to completion")
    args = parser.parse_args()
    conn = sqlite3.connect(args.db)
    conn.executescript("""
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
    state = conn.execute("SELECT offset,complete FROM progress WHERE source='oath_dob_descriptions'").fetchone()
    offset = state[0] if state else 0
    if state and state[1]:
        print("OATH DOB description mining already complete")
        return
    pages = 0
    while True:
        rows = query(offset, args.batch_size)
        output = []
        for row in rows:
            parts = [str(row.get(field) or "").strip() for field in ("violation_description", "violation_details")]
            description = " ".join(dict.fromkeys(part for part in parts if part))
            labels = extract_explicit_unit_labels(description)
            address = " ".join(
                str(row.get(field) or "").strip().upper()
                for field in ("violation_location_house", "violation_location_street_name")
                if row.get(field)
            )
            output.append((
                str(row.get("ticket_number") or ""),
                make_bbl(row.get("violation_location_borough"), row.get("violation_location_block_no"),
                         row.get("violation_location_lot_no")),
                address, str(row.get("violation_location_zip_code") or ""), description,
                str(row.get("violation_date") or ""), json.dumps(labels),
                "explicit_candidate" if labels else "ambiguous_unit_word",
            ))
        conn.executemany(
            "INSERT OR REPLACE INTO descriptions "
            "(job_filing_number,bbl,address,zipcode,description,filing_date,extracted_labels,status) "
            "VALUES (?,?,?,?,?,?,?,?)", output,
        )
        offset += len(rows)
        complete = int(len(rows) < args.batch_size)
        conn.execute(
            "INSERT INTO progress(source,offset,complete,updated_at) VALUES (?,?,?,datetime('now')) "
            "ON CONFLICT(source) DO UPDATE SET offset=excluded.offset,complete=excluded.complete,updated_at=excluded.updated_at",
            ("oath_dob_descriptions", offset, complete),
        )
        conn.commit()
        explicit = conn.execute("SELECT COUNT(*) FROM descriptions WHERE status='explicit_candidate'").fetchone()[0]
        resolved = conn.execute("SELECT COUNT(*) FROM descriptions WHERE status='explicit_candidate' AND bbl!=''").fetchone()[0]
        print(f"offset={offset} explicit_candidates={explicit} with_bbl={resolved}", flush=True)
        if complete:
            break
        pages += 1
        if args.pages is not None and pages >= args.pages:
            break
        time.sleep(0.25)
    conn.close()


if __name__ == "__main__":
    main()
