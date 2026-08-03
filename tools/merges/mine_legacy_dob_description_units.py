#!/usr/bin/env python3
"""Collect apartment labels from legacy DOB job descriptions (2000 onward)."""
import argparse
import json
import re
import sqlite3
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API = "https://data.cityofnewyork.us/resource/ic3t-wcy2.json"
WHERE = (
    "job_description IS NOT NULL AND (upper(job_description) like '%APT%' "
    "OR upper(job_description) like '%DWELLING UNIT%' "
    "OR upper(job_description) like '%RESIDENTIAL UNIT%')"
)
LABEL_RE = re.compile(
    r"\b(?:APT|APARTMENT|DWELLING\s+UNIT|RESIDENTIAL\s+UNIT)\s*(?:NO\.?\s*|#\s*)?"
    r"([A-Z]?\d[A-Z0-9-]{0,7}|\d+[A-Z][A-Z0-9-]{0,7})\b",
    re.IGNORECASE,
)
BORO = {"MANHATTAN": "1", "BRONX": "2", "BROOKLYN": "3", "QUEENS": "4", "STATEN ISLAND": "5"}


def make_bbl(borough, block, lot):
    boro = BORO.get(str(borough or "").strip().upper(), "")
    block_digits = "".join(char for char in str(block or "") if char.isdigit())
    lot_digits = "".join(char for char in str(lot or "") if char.isdigit())
    if not boro or not block_digits or not lot_digits:
        return ""
    return boro + block_digits.zfill(5) + lot_digits.zfill(4)


def query(offset, limit):
    params = urlencode({
        "$select": "job_s1_no,borough,block,lot,house__,street_name,job_description,latest_action_date",
        "$where": WHERE, "$order": "job_s1_no", "$limit": limit, "$offset": offset,
    })
    request = Request(f"{API}?{params}", headers={"User-Agent": "pricefixed-public-records/1.0"})
    with urlopen(request, timeout=180) as response:
        return json.loads(response.read())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--batch-size", type=int, default=50000)
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
    state = conn.execute("SELECT offset,complete FROM progress WHERE source='legacy_dob_descriptions'").fetchone()
    offset = state[0] if state else 0
    if state and state[1]:
        print("legacy DOB description mining already complete")
        return
    while True:
        rows = query(offset, args.batch_size)
        output = []
        for row in rows:
            description = str(row.get("job_description") or "").strip()
            labels = list(dict.fromkeys(match.upper() for match in LABEL_RE.findall(description)))
            address = " ".join(
                str(row.get(field) or "").strip().upper()
                for field in ("house__", "street_name") if row.get(field)
            )
            output.append((
                str(row.get("job_s1_no") or ""),
                make_bbl(row.get("borough"), row.get("block"), row.get("lot")),
                address, "", description, str(row.get("latest_action_date") or ""),
                json.dumps(labels), "explicit_candidate" if labels else "ambiguous_unit_word",
            ))
        conn.executemany(
            "INSERT OR REPLACE INTO descriptions "
            "(job_filing_number,bbl,address,zipcode,description,filing_date,extracted_labels,status) "
            "VALUES (?,?,?,?,?,?,?,?)", output,
        )
        offset += len(rows)
        complete = int(len(rows) < args.batch_size)
        conn.execute(
            "INSERT INTO progress(source,offset,complete,updated_at) "
            "VALUES ('legacy_dob_descriptions',?,?,datetime('now')) ON CONFLICT(source) DO UPDATE SET "
            "offset=excluded.offset,complete=excluded.complete,updated_at=excluded.updated_at",
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
