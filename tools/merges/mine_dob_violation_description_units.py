#!/usr/bin/env python3
"""Collect apartment-label candidates from official legacy DOB violations."""
import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.engine.unit_mentions import extract_explicit_unit_labels


DATASET = "3h2n-5cm9"
API = f"https://data.cityofnewyork.us/resource/{DATASET}.json"
TEXT_FILTER = (
    "(upper(description) like '%APT%' OR upper(description) like '%APARTMENT%' OR "
    "upper(disposition_comments) like '%APT%' OR upper(disposition_comments) like '%APARTMENT%')"
)
WHERE = f"{TEXT_FILTER} AND boro is not null AND block is not null AND lot is not null"


def make_bbl(borough, block, lot):
    boro = "".join(char for char in str(borough or "") if char.isdigit())
    block = "".join(char for char in str(block or "") if char.isdigit())
    lot = "".join(char for char in str(lot or "") if char.isdigit())
    if boro not in {"1", "2", "3", "4", "5"} or not block or not lot:
        return ""
    return boro + block.zfill(5)[-5:] + lot.zfill(4)[-4:]


def compact_date(value):
    digits = "".join(char for char in str(value or "") if char.isdigit())
    if len(digits) != 8:
        return ""
    try:
        return datetime.strptime(digits, "%Y%m%d").date().isoformat()
    except ValueError:
        return ""


def query(offset, limit):
    fields = (
        "isn_dob_bis_viol,boro,block,lot,issue_date,house_number,street,"
        "description,disposition_comments"
    )
    params = urlencode({
        "$select": fields, "$where": WHERE, "$order": "isn_dob_bis_viol",
        "$limit": limit, "$offset": offset,
    })
    request = Request(f"{API}?{params}", headers={"User-Agent": "pricefixed-public-records/1.0"})
    with urlopen(request, timeout=180) as response:
        return json.loads(response.read())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--batch-size", type=int, default=25000)
    parser.add_argument("--pages", type=int, help="bound this run; omit to resume to completion")
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
    progress_source = "dob_violation_descriptions"
    state = connection.execute(
        "SELECT offset,complete FROM progress WHERE source=?", (progress_source,)
    ).fetchone()
    offset = state[0] if state else 0
    if state and state[1]:
        print("DOB violation description mining already complete")
        return
    pages = 0
    while True:
        rows = query(offset, args.batch_size)
        output = []
        for row in rows:
            parts = [str(row.get(field) or "").strip() for field in ("description", "disposition_comments")]
            description = " ".join(dict.fromkeys(part for part in parts if part))
            labels = extract_explicit_unit_labels(description)
            address = " ".join(
                str(row.get(field) or "").strip().upper()
                for field in ("house_number", "street") if row.get(field)
            )
            output.append((
                str(row.get("isn_dob_bis_viol") or ""),
                make_bbl(row.get("boro"), row.get("block"), row.get("lot")),
                address, "", description, compact_date(row.get("issue_date")),
                json.dumps(labels), "explicit_candidate" if labels else "ambiguous_unit_word",
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
            (progress_source, offset, complete),
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
        time.sleep(0.25)
    connection.close()


if __name__ == "__main__":
    main()
