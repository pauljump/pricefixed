#!/usr/bin/env python3
"""Measure anonymized NYC unit candidates in Campaign Finance mailing addresses.

This is deliberately a staging audit, not a catalog merger. It reads only address,
unit, date, and Socrata row ID fields; names and payment details are never requested.
Candidates require an exact unique PAD address-and-ZIP match and a residential PLUTO
building. Net-new rows remain marked ``policy_review``.
"""
import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.engine.crosswalk import normalize_address
from tools.merges.prepare_public_unit_candidates import usable_dwelling_label


DATASET = "qxzj-vkn2"
API = f"https://data.cityofnewyork.us/resource/{DATASET}.json"
SOURCE = "campaign_finance_expenditure_addresses"
WHERE = (
    "apartment is not null AND trim(apartment) != '' AND "
    "upper(state)='NY' AND c_code='IND'"
)
GROUP_FIELDS = "strno,strname,apartment,city,state,zip"


def query_page(offset, limit):
    params = urlencode({
        "$select": (
            f"{GROUP_FIELDS},min(:id) as source_ref,max(date) as observed_at,"
            "count(*) as source_rows"
        ),
        "$where": WHERE,
        "$group": GROUP_FIELDS,
        "$order": GROUP_FIELDS,
        "$limit": limit,
        "$offset": offset,
    })
    url = f"{API}?{params}"
    request = Request(url, headers={"User-Agent": "pricefixed-public-records/1.0"})
    for attempt in range(5):
        try:
            with urlopen(request, timeout=180) as response:
                return json.loads(response.read()), url
        except HTTPError as exc:
            if exc.code < 500 and exc.code != 429:
                raise
            if attempt == 4:
                raise
        except (URLError, TimeoutError):
            if attempt == 4:
                raise
        time.sleep(2 ** attempt)
    raise RuntimeError("unreachable campaign finance retry state")


def resolve_residential_pad_bbl(catalog, address, zipcode):
    normalized = normalize_address(address)
    zipcode = "".join(char for char in str(zipcode or "") if char.isdigit())[:5]
    if not normalized or len(zipcode) != 5:
        return ""
    rows = catalog.execute(
        "SELECT DISTINCT a.bbl FROM addresses a JOIN buildings b ON b.bbl=a.bbl "
        "WHERE a.normalized=? AND a.zipcode=? AND a.source='nyc_pad' "
        "AND COALESCE(b.units_res,0)>0",
        (normalized, zipcode),
    ).fetchall()
    return rows[0][0] if len(rows) == 1 else ""


def init_db(connection):
    connection.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS candidates (
            bbl TEXT NOT NULL, normalized_unit TEXT NOT NULL, unit_label TEXT NOT NULL,
            address TEXT NOT NULL, zipcode TEXT NOT NULL, dataset TEXT NOT NULL,
            source_ref TEXT NOT NULL, observed_at TEXT, source_rows INTEGER NOT NULL,
            source_url TEXT NOT NULL, status TEXT NOT NULL,
            PRIMARY KEY(bbl,normalized_unit)
        );
        CREATE TABLE IF NOT EXISTS progress (
            source TEXT PRIMARY KEY, offset INTEGER NOT NULL, complete INTEGER NOT NULL,
            invalid_labels INTEGER NOT NULL, unmatched_addresses INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)


def summary(connection):
    state = connection.execute(
        "SELECT offset,complete,invalid_labels,unmatched_addresses FROM progress WHERE source=?",
        (SOURCE,),
    ).fetchone() or (0, 0, 0, 0)
    return {
        "dataset": DATASET,
        "grouped_source_rows": state[0],
        "complete": bool(state[1]),
        "invalid_or_non_dwelling_labels": state[2],
        "unmatched_or_nonresidential_addresses": state[3],
        "unique_matched_candidates": connection.execute(
            "SELECT COUNT(*) FROM candidates"
        ).fetchone()[0],
        "net_new_policy_review": connection.execute(
            "SELECT COUNT(*) FROM candidates WHERE status='policy_review'"
        ).fetchone()[0],
        "already_in_catalog": connection.execute(
            "SELECT COUNT(*) FROM candidates WHERE status='already_in_catalog'"
        ).fetchone()[0],
        "catalog_writes": 0,
        "privacy": "No names, transaction amounts, employers, or occupations were requested or stored.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--catalog-db", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--batch-size", type=int, default=25000)
    parser.add_argument("--pages", type=int)
    args = parser.parse_args()
    if args.batch_size <= 0 or (args.pages is not None and args.pages <= 0):
        parser.error("--batch-size and --pages must be positive")
    connection = sqlite3.connect(args.db)
    init_db(connection)
    catalog = sqlite3.connect(f"file:{Path(args.catalog_db).resolve()}?mode=ro", uri=True)
    state = connection.execute(
        "SELECT offset,complete,invalid_labels,unmatched_addresses FROM progress WHERE source=?",
        (SOURCE,),
    ).fetchone()
    offset, complete, invalid, unmatched = state or (0, 0, 0, 0)
    pages = 0
    while not complete:
        rows, source_url = query_page(offset, args.batch_size)
        accepted = []
        for row in rows:
            raw_label = " ".join(str(row.get("apartment") or "").strip().upper().split())
            normalized_unit = usable_dwelling_label(SOURCE, raw_label)
            if not normalized_unit:
                invalid += 1
                continue
            address = " ".join(
                str(row.get(field) or "").strip().upper()
                for field in ("strno", "strname") if row.get(field)
            )
            zipcode = "".join(char for char in str(row.get("zip") or "") if char.isdigit())[:5]
            bbl = resolve_residential_pad_bbl(catalog, address, zipcode)
            if not bbl:
                unmatched += 1
                continue
            exists = catalog.execute(
                "SELECT 1 FROM units WHERE bbl=? AND normalized_unit=? LIMIT 1",
                (bbl, normalized_unit),
            ).fetchone()
            accepted.append((
                bbl, normalized_unit, raw_label, address, zipcode, DATASET,
                str(row.get("source_ref") or ""), str(row.get("observed_at") or ""),
                int(row.get("source_rows") or 0), source_url,
                "already_in_catalog" if exists else "policy_review",
            ))
        connection.executemany(
            "INSERT OR IGNORE INTO candidates "
            "(bbl,normalized_unit,unit_label,address,zipcode,dataset,source_ref,observed_at,"
            "source_rows,source_url,status) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            accepted,
        )
        offset += len(rows)
        complete = int(len(rows) < args.batch_size)
        connection.execute(
            "INSERT INTO progress(source,offset,complete,invalid_labels,unmatched_addresses,updated_at) "
            "VALUES (?,?,?,?,?,datetime('now')) ON CONFLICT(source) DO UPDATE SET "
            "offset=excluded.offset,complete=excluded.complete,invalid_labels=excluded.invalid_labels,"
            "unmatched_addresses=excluded.unmatched_addresses,updated_at=excluded.updated_at",
            (SOURCE, offset, complete, invalid, unmatched),
        )
        connection.commit()
        print(json.dumps(summary(connection), sort_keys=True), flush=True)
        pages += 1
        if args.pages is not None and pages >= args.pages:
            break
    result = summary(connection)
    Path(args.summary).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    catalog.close()
    connection.close()


if __name__ == "__main__":
    main()
