#!/usr/bin/env python3
"""Collect explicit dwelling/residential-unit markers skipped by apt-only filters."""
import argparse
import json
import sqlite3
import sys
import time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.engine.unit_mentions import extract_explicit_unit_labels


BOROUGH = {
    "MANHATTAN": "1", "BRONX": "2", "BROOKLYN": "3", "QUEENS": "4",
    "STATEN IS": "5", "STATEN ISLAND": "5",
}

SOURCES = {
    "dcp": {
        "dataset": "br6q-ssj3", "id": "job_number", "texts": ("job_desc",),
        "fields": ("bbl", "addressnum", "addressst", "datefiled"),
        "base": "bbl is not null",
        "old": "(upper(job_desc) like '%APT %' OR upper(job_desc) like '%APT.%' OR upper(job_desc) like '%APT#%' OR upper(job_desc) like '%APARTMENT%')",
        "bbl": ("bbl",), "address": ("addressnum", "addressst"), "date": "datefiled",
    },
    "approved_permit": {
        "dataset": "rbx6-tga4", "id": "work_permit", "texts": ("job_description",),
        "fields": ("sequence_number", "bbl", "house_no", "street_name", "issued_date"),
        "base": "bbl is not null AND (apt_condo_no_s is null OR trim(apt_condo_no_s)='')",
        "old": "(upper(job_description) like '%APT %' OR upper(job_description) like '%APT.%' OR upper(job_description) like '%APT#%' OR upper(job_description) like '%APARTMENT%')",
        "bbl": ("bbl",), "address": ("house_no", "street_name"), "date": "issued_date",
    },
    "electrical": {
        "dataset": "dm9a-ab7w", "id": "job_filing_number", "texts": ("job_description",),
        "fields": ("gis_bbl", "house_number", "street_name", "filing_date"),
        "base": "gis_bbl is not null",
        "old": "(upper(job_description) like '%APT %' OR upper(job_description) like '%APT.%' OR upper(job_description) like '%APT#%' OR upper(job_description) like '%APARTMENT%')",
        "bbl": ("gis_bbl",), "address": ("house_number", "street_name"), "date": "filing_date",
    },
    "dob_violation": {
        "dataset": "3h2n-5cm9", "id": "isn_dob_bis_viol",
        "texts": ("description", "disposition_comments"),
        "fields": ("boro", "block", "lot", "house_number", "street", "issue_date"),
        "base": "boro is not null AND block is not null AND lot is not null",
        "old": "(upper(description) like '%APT%' OR upper(description) like '%APARTMENT%' OR upper(disposition_comments) like '%APT%' OR upper(disposition_comments) like '%APARTMENT%')",
        "bbl": ("boro", "block", "lot"), "address": ("house_number", "street"),
        "date": "issue_date", "compact_date": True,
    },
    "ecb": {
        "dataset": "6bgk-3dad", "id": "ecb_violation_number",
        "texts": ("violation_description",),
        "fields": ("boro", "block", "lot", "issue_date"),
        "base": "boro is not null AND block is not null AND lot is not null",
        "old": "(upper(violation_description) like '%APT%' OR upper(violation_description) like '%APARTMENT%')",
        "bbl": ("boro", "block", "lot"), "address": (), "date": "issue_date",
        "compact_date": True,
    },
    "oath": {
        "dataset": "jz4z-kudi", "id": "ticket_number",
        "texts": ("violation_description", "violation_details"),
        "fields": ("violation_location_borough", "violation_location_block_no",
                   "violation_location_lot_no", "violation_location_house",
                   "violation_location_street_name", "violation_date"),
        "base": "issuing_agency='DEPT. OF BUILDINGS'",
        "old": "(upper(violation_description) like '%APT%' OR upper(violation_description) like '%APARTMENT%' OR upper(violation_details) like '%APT%' OR upper(violation_details) like '%APARTMENT%')",
        "bbl": ("violation_location_borough", "violation_location_block_no",
                "violation_location_lot_no"),
        "address": ("violation_location_house", "violation_location_street_name"),
        "date": "violation_date",
    },
}


def normalize_bbl(*values):
    if len(values) == 1:
        text = str(values[0] or "").strip()
        if text.endswith(".0"):
            text = text[:-2]
        digits = "".join(char for char in text if char.isdigit())
        return digits if len(digits) == 10 and digits[0] in "12345" else ""
    borough, block, lot = values
    boro_text = str(borough or "").strip().upper()
    boro = BOROUGH.get(boro_text, "".join(char for char in boro_text if char.isdigit()))
    block = "".join(char for char in str(block or "") if char.isdigit())
    lot = "".join(char for char in str(lot or "") if char.isdigit())
    if boro not in {"1", "2", "3", "4", "5"} or not block or not lot:
        return ""
    return boro + block.zfill(5)[-5:] + lot.zfill(4)[-4:]


def observed_date(value, compact=False):
    text = str(value or "").strip()
    if compact:
        digits = "".join(char for char in text if char.isdigit())
        try:
            return datetime.strptime(digits, "%Y%m%d").date().isoformat()
        except ValueError:
            return ""
    for candidate, pattern in ((text[:10], "%Y-%m-%d"), (text[:10], "%m/%d/%Y")):
        try:
            return datetime.strptime(candidate, pattern).date().isoformat()
        except ValueError:
            pass
    return ""


def where_clause(config):
    new = []
    for field in config["texts"]:
        new.extend((
            f"upper({field}) like '%DWELLING UNIT%'",
            f"upper({field}) like '%RESIDENTIAL UNIT%'",
        ))
    return f"{config['base']} AND ({' OR '.join(new)}) AND NOT {config['old']}"


def query(config, offset, limit):
    fields = list(dict.fromkeys((config["id"],) + config["fields"] + config["texts"]))
    params = urlencode({
        "$select": ",".join(fields), "$where": where_clause(config),
        "$order": config["id"], "$limit": limit, "$offset": offset,
    })
    request = Request(
        f"https://data.cityofnewyork.us/resource/{config['dataset']}.json?{params}",
        headers={"User-Agent": "pricefixed-public-records/1.0"},
    )
    with urlopen(request, timeout=180) as response:
        return json.loads(response.read())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=sorted(SOURCES), required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--batch-size", type=int, default=25000)
    parser.add_argument("--pages", type=int)
    args = parser.parse_args()
    if args.batch_size <= 0 or (args.pages is not None and args.pages <= 0):
        sys.exit("--batch-size and --pages must be positive")
    config = SOURCES[args.source]
    progress_source = f"dwelling_unit_marker_delta_{args.source}"
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
    state = connection.execute(
        "SELECT offset,complete FROM progress WHERE source=?", (progress_source,)
    ).fetchone()
    offset = state[0] if state else 0
    if state and state[1]:
        print(f"{args.source} dwelling-unit marker delta already complete")
        connection.close()
        return
    pages = 0
    while True:
        rows = query(config, offset, args.batch_size)
        output = []
        for row in rows:
            parts = [str(row.get(field) or "").strip() for field in config["texts"]]
            description = " ".join(dict.fromkeys(part for part in parts if part))
            labels = extract_explicit_unit_labels(description)
            address = " ".join(
                str(row.get(field) or "").strip().upper()
                for field in config["address"] if row.get(field)
            )
            output.append((
                str(row.get(config["id"]) or ""),
                normalize_bbl(*(row.get(field) for field in config["bbl"])),
                address, "", description,
                observed_date(row.get(config["date"]), config.get("compact_date", False)),
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
        print(f"source={args.source} offset={offset} explicit_candidates={explicit}", flush=True)
        if complete:
            break
        pages += 1
        if args.pages is not None and pages >= args.pages:
            break
        time.sleep(0.25)
    connection.close()


if __name__ == "__main__":
    main()
