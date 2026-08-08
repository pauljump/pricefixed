#!/usr/bin/env python3
"""Collect DOB job descriptions that may name apartments outside the unit field."""
import argparse
import json
import re
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API = "https://data.cityofnewyork.us/resource/w9ak-ipjd.json"
WHERE = (
    "(apt_condo_no_s IS NULL OR apt_condo_no_s='') AND job_description IS NOT NULL AND "
    "(upper(job_description) like '%APT%' OR upper(job_description) like '%APARTMENT%' "
    "OR upper(job_description) like '%UNIT%')"
)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.engine.unit_mentions import extract_explicit_unit_labels


def normalize_bbl(value):
    digits = "".join(char for char in str(value or "").split(".", 1)[0] if char.isdigit())
    return digits if len(digits) == 10 and digits[0] in "12345" else ""


def query(offset, limit):
    params = urlencode({
        "$select": "job_filing_number,bbl,house_no,street_name,postcode,job_description,filing_date",
        "$where": WHERE,
        "$order": "job_filing_number",
        "$limit": limit,
        "$offset": offset,
    })
    request = Request(f"{API}?{params}", headers={"User-Agent": "pricefixed-public-records/1.0"})
    with urlopen(request, timeout=180) as response:
        return json.loads(response.read())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--batch-size", type=int, default=50000)
    parser.add_argument("--reclassify", action="store_true", help="Reparse stored descriptions without downloading")
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
    state = conn.execute("SELECT offset,complete FROM progress WHERE source='dob_descriptions'").fetchone()
    offset = state[0] if state else 0
    if state and state[1] and args.reclassify:
        rows = conn.execute("SELECT job_filing_number,description FROM descriptions")
        updates = []
        for job, description in rows:
            labels = extract_explicit_unit_labels(description)
            updates.append((json.dumps(labels), "explicit_candidate" if labels else "ambiguous_unit_word", job))
            if len(updates) >= 10000:
                conn.executemany("UPDATE descriptions SET extracted_labels=?,status=? WHERE job_filing_number=?", updates)
                conn.commit()
                updates = []
        if updates:
            conn.executemany("UPDATE descriptions SET extracted_labels=?,status=? WHERE job_filing_number=?", updates)
            conn.commit()
        explicit = conn.execute("SELECT COUNT(*) FROM descriptions WHERE status='explicit_candidate'").fetchone()[0]
        print(f"reclassified stored DOB descriptions; explicit_candidates={explicit}")
        conn.close()
        return
    if state and state[1]:
        print("DOB description mining already complete")
        return
    while True:
        rows = query(offset, args.batch_size)
        output = []
        for row in rows:
            description = str(row.get("job_description") or "").strip()
            labels = extract_explicit_unit_labels(description)
            address = " ".join(str(row.get(field) or "").strip().upper()
                               for field in ("house_no", "street_name") if row.get(field))
            output.append((str(row.get("job_filing_number") or ""), normalize_bbl(row.get("bbl")),
                           address, str(row.get("postcode") or ""), description,
                           str(row.get("filing_date") or ""), json.dumps(labels),
                           "explicit_candidate" if labels else "ambiguous_unit_word"))
        conn.executemany(
            "INSERT OR REPLACE INTO descriptions "
            "(job_filing_number,bbl,address,zipcode,description,filing_date,extracted_labels,status) "
            "VALUES (?,?,?,?,?,?,?,?)", output,
        )
        offset += len(rows)
        complete = int(len(rows) < args.batch_size)
        conn.execute(
            "INSERT INTO progress(source,offset,complete,updated_at) VALUES ('dob_descriptions',?,?,datetime('now')) "
            "ON CONFLICT(source) DO UPDATE SET offset=excluded.offset,complete=excluded.complete,updated_at=excluded.updated_at",
            (offset, complete),
        )
        conn.commit()
        explicit = conn.execute("SELECT COUNT(*) FROM descriptions WHERE status='explicit_candidate'").fetchone()[0]
        print(f"offset={offset} explicit_candidates={explicit}", flush=True)
        if complete:
            break
        time.sleep(0.25)
    conn.close()


if __name__ == "__main__":
    main()
