#!/usr/bin/env python3
"""Mine compact, deduplicated unit mentions from official NYC event datasets."""
import argparse
import json
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API = "https://data.cityofnewyork.us/resource"
SOURCES = {
    "dob_jobs": {
        "dataset": "w9ak-ipjd", "bbl": "bbl", "boro": "borough", "block": "block", "lot": "lot",
        "address": ("house_no", "street_name"), "zip": "postcode", "unit": "apt_condo_no_s",
        "ref": "job_filing_number", "date": "filing_date",
    },
    "dob_permits": {
        "dataset": "rbx6-tga4", "bbl": "bbl", "boro": "borough", "block": "block", "lot": "lot",
        "address": ("house_no", "street_name"), "zip": "zip_code", "unit": "apt_condo_no_s",
        "ref": "work_permit", "date": "issued_date",
    },
    "hpd_violations": {
        "dataset": "wvxf-dwi5", "bbl": None, "boro": "boroid", "block": "block", "lot": "lot",
        "address": ("housenumber", "streetname"), "zip": "zip", "unit": "apartment",
        "ref": "violationid", "date": "novissueddate",
    },
    "hpd_problems": {
        "dataset": "ygpa-z7cr", "bbl": "bbl", "boro": None, "block": "block", "lot": "lot",
        "address": ("house_number", "street_name"), "zip": "post_code", "unit": "apartment",
        "ref": "problem_id", "date": "received_date",
    },
    "hpd_omo": {
        "dataset": "mdbu-nrqn", "bbl": "bbl", "boro": "boro_id", "block": "block", "lot": "lot",
        "address": ("housenumber", "streetname"), "zip": "zip", "unit": "apartment",
        "ref": "omoid", "date": "omocreatedate",
    },
    "nycha_violations": {
        "dataset": "im9z-53hg", "bbl": "bbl", "boro": "boro", "block": "blk", "lot": "lot",
        "address": ("phn", "str_nm"), "zip": "zip", "unit": "actl_unit_insp",
        "ref": "viol_seq_no", "date": "insp_dt",
    },
}


def normalized_bbl(row, config):
    direct = str(row.get(config["bbl"]) or "").split(".", 1)[0] if config["bbl"] else ""
    digits = "".join(char for char in direct if char.isdigit())
    if len(digits) == 10 and digits[0] in "12345":
        return digits
    boro = "".join(char for char in str(row.get(config["boro"]) or "") if char.isdigit())
    block = "".join(char for char in str(row.get(config["block"]) or "") if char.isdigit())
    lot = "".join(char for char in str(row.get(config["lot"]) or "") if char.isdigit())
    if len(boro) == 1 and boro in "12345" and block and lot:
        return boro + block.zfill(5) + lot.zfill(4)
    return ""


def query_page(config, offset, limit):
    group_fields = [field for field in (
        config["bbl"], config["boro"], config["block"], config["lot"],
        *config["address"], config["zip"], config["unit"],
    ) if field]
    select = ",".join(group_fields + [
        f"min({config['ref']}) as source_ref", f"max({config['date']}) as observed_at"
    ])
    params = urlencode({
        "$select": select,
        "$where": f"{config['unit']} IS NOT NULL AND {config['unit']} != ''",
        "$group": ",".join(group_fields),
        "$order": ",".join(group_fields),
        "$limit": limit,
        "$offset": offset,
    })
    url = f"{API}/{config['dataset']}.json?{params}"
    request = Request(url, headers={"User-Agent": "pricefixed-public-records/1.0"})
    with urlopen(request, timeout=180) as response:
        return json.loads(response.read()), url


def init_db(conn):
    conn.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS mentions (
            source TEXT NOT NULL, source_ref TEXT NOT NULL, bbl TEXT NOT NULL,
            address TEXT NOT NULL, zipcode TEXT, unit_label TEXT NOT NULL,
            observed_at TEXT, dataset TEXT NOT NULL, source_url TEXT NOT NULL,
            PRIMARY KEY(source,bbl,address,unit_label)
        );
        CREATE INDEX IF NOT EXISTS idx_mentions_bbl ON mentions(bbl);
        CREATE TABLE IF NOT EXISTS progress (
            source TEXT PRIMARY KEY, offset INTEGER NOT NULL, complete INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)


def mine_source(conn, name, batch_size):
    config = SOURCES[name]
    state = conn.execute("SELECT offset,complete FROM progress WHERE source=?", (name,)).fetchone()
    offset = state[0] if state else 0
    if state and state[1]:
        print(f"{name}: already complete", flush=True)
        return
    while True:
        rows, source_url = query_page(config, offset, batch_size)
        accepted = []
        for row in rows:
            bbl = normalized_bbl(row, config)
            unit = " ".join(str(row.get(config["unit"]) or "").strip().upper().split())
            address = " ".join(
                str(row.get(field) or "").strip().upper() for field in config["address"] if row.get(field)
            )
            if not bbl or not unit or not address:
                continue
            accepted.append((name, str(row.get("source_ref") or ""), bbl, address,
                             str(row.get(config["zip"]) or ""), unit,
                             str(row.get("observed_at") or ""), config["dataset"], source_url))
        conn.executemany(
            "INSERT OR IGNORE INTO mentions "
            "(source,source_ref,bbl,address,zipcode,unit_label,observed_at,dataset,source_url) "
            "VALUES (?,?,?,?,?,?,?,?,?)", accepted,
        )
        offset += len(rows)
        complete = int(len(rows) < batch_size)
        conn.execute(
            "INSERT INTO progress(source,offset,complete,updated_at) VALUES (?,?,?,datetime('now')) "
            "ON CONFLICT(source) DO UPDATE SET offset=excluded.offset,complete=excluded.complete,updated_at=excluded.updated_at",
            (name, offset, complete),
        )
        conn.commit()
        total = conn.execute("SELECT COUNT(*) FROM mentions WHERE source=?", (name,)).fetchone()[0]
        print(f"{name}: offset={offset} distinct_mentions={total}", flush=True)
        if complete:
            return
        time.sleep(0.25)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--sources", nargs="+", choices=sorted(SOURCES), default=sorted(SOURCES))
    parser.add_argument("--batch-size", type=int, default=50000)
    args = parser.parse_args()
    conn = sqlite3.connect(args.db)
    init_db(conn)
    for source in args.sources:
        mine_source(conn, source, args.batch_size)
    conn.close()


if __name__ == "__main__":
    main()
