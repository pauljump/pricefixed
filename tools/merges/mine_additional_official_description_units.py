#!/usr/bin/env python3
"""Collect unit labels from additional direct-BBL NYC agency descriptions."""
import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.engine.unit_mentions import extract_explicit_unit_labels


SOURCES = {
    "laa": {
        "dataset": "xxbr-ypig", "id": ("job_number", "filing_number", "permit_number"),
        "text": "proposed_work_summary",
        "fields": ("bbl", "location_house_no", "location_street_name", "zip_code", "filing_date"),
        "base": "bbl is not null", "bbl": ("bbl",),
        "address": ("location_house_no", "location_street_name"),
        "zip": "zip_code", "date": "filing_date",
    },
    "hpd_violation_blank": {
        "dataset": "wvxf-dwi5", "id": ("violationid",), "text": "novdescription",
        "fields": ("bbl", "housenumber", "streetname", "zip", "novissueddate"),
        "base": "bbl is not null AND (apartment is null OR apartment='')", "bbl": ("bbl",),
        "address": ("housenumber", "streetname"), "zip": "zip", "date": "novissueddate",
    },
    "nycha_violation_blank": {
        "dataset": "im9z-53hg", "id": ("viol_seq_no",), "text": "viol_desc",
        "fields": ("bbl", "phn", "str_nm", "zip", "insp_dt"),
        "base": "bbl is not null AND (actl_unit_insp is null OR actl_unit_insp='')",
        "bbl": ("bbl",),
        "address": ("phn", "str_nm"), "zip": "zip", "date": "insp_dt",
    },
    "elevator_application": {
        "dataset": "kfp4-dz4h", "id": ("job_filing_number",), "text": "descriptionofwork",
        "fields": ("bbl", "house_number", "street_name", "zip", "filing_date"),
        "base": "bbl is not null", "bbl": ("bbl",),
        "address": ("house_number", "street_name"),
        "zip": "zip", "date": "filing_date",
    },
    "landmark_complaint": {
        "dataset": "ck4n-5h6x", "id": ("complaint",), "text": "work_reported",
        "fields": ("borough", "block", "lot", "address", "street_name", "postcode", "date"),
        "base": "borough is not null AND block is not null AND lot is not null",
        "bbl": ("borough", "block", "lot"), "address": ("address", "street_name"),
        "zip": "postcode", "date": "date",
    },
}

BOROUGH = {
    "MANHATTAN": "1", "BRONX": "2", "BROOKLYN": "3", "QUEENS": "4",
    "STATEN IS": "5", "STATEN ISLAND": "5",
}


def normalize_bbl(*values):
    if len(values) == 1:
        text = str(values[0] or "").strip()
        if text.endswith(".0"):
            text = text[:-2]
        digits = "".join(char for char in text if char.isdigit())
        return digits if len(digits) == 10 and digits[0] in "12345" else ""
    borough, block, lot = values
    boro = BOROUGH.get(str(borough or "").strip().upper(), "")
    block = "".join(char for char in str(block or "") if char.isdigit())
    lot = "".join(char for char in str(lot or "") if char.isdigit())
    if not boro or not block or not lot:
        return ""
    return boro + block.zfill(5)[-5:] + lot.zfill(4)[-4:]


def observed_date(value):
    text = str(value or "").strip()[:10]
    for pattern in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            pass
    return ""


def where_clause(config):
    field = config["text"]
    markers = (
        f"upper({field}) like '%APT%'", f"upper({field}) like '%APARTMENT%'",
        f"upper({field}) like '%DWELLING UNIT%'",
        f"upper({field}) like '%RESIDENTIAL UNIT%'",
    )
    return f"{config['base']} AND ({' OR '.join(markers)})"


def query(config, offset, limit):
    fields = list(dict.fromkeys(config["id"] + config["fields"] + (config["text"],)))
    params = urlencode({
        "$select": ",".join(fields), "$where": where_clause(config),
        "$order": ",".join(config["id"]), "$limit": limit, "$offset": offset,
    })
    request = Request(
        f"https://data.cityofnewyork.us/resource/{config['dataset']}.json?{params}",
        headers={"User-Agent": "pricefixed-public-records/1.0"},
    )
    for attempt in range(5):
        try:
            with urlopen(request, timeout=180) as response:
                return json.loads(response.read())
        except HTTPError as exc:
            if exc.code < 500 and exc.code != 429:
                raise
            if attempt == 4:
                raise
        except (URLError, TimeoutError):
            if attempt == 4:
                raise
        time.sleep(2 ** attempt)
    raise RuntimeError("unreachable query retry state")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=sorted(SOURCES), required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--batch-size", type=int, default=10000)
    parser.add_argument("--pages", type=int)
    args = parser.parse_args()
    if args.batch_size <= 0 or (args.pages is not None and args.pages <= 0):
        sys.exit("--batch-size and --pages must be positive")
    config = SOURCES[args.source]
    progress_source = f"additional_official_description_{args.source}"
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
        print(f"{args.source} description mining already complete")
        connection.close()
        return
    pages = 0
    while True:
        rows = query(config, offset, args.batch_size)
        output = []
        for row in rows:
            description = str(row.get(config["text"]) or "").strip()
            labels = extract_explicit_unit_labels(description)
            source_ref = "|".join(str(row.get(field) or "").strip() for field in config["id"])
            if not source_ref.strip("|"):
                continue
            address = " ".join(
                str(row.get(field) or "").strip().upper()
                for field in config["address"] if row.get(field)
            )
            output.append((
                source_ref,
                normalize_bbl(*(row.get(field) for field in config["bbl"])), address,
                str(row.get(config["zip"]) or ""), description,
                observed_date(row.get(config["date"])), json.dumps(labels),
                "explicit_candidate" if labels else "ambiguous_unit_word",
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
