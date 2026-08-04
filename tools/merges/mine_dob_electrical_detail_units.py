#!/usr/bin/env python3
"""Collect apartment labels from DOB NOW electrical permit detail rows."""
import argparse
import json
import re
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.engine.unit_mentions import extract_explicit_unit_labels


DETAIL_DATASET = "xmmq-y7za"
DETAIL_API = f"https://data.cityofnewyork.us/resource/{DETAIL_DATASET}.json"
PARENT_DATASET = "dm9a-ab7w"
PARENT_API = f"https://data.cityofnewyork.us/resource/{PARENT_DATASET}.json"
DETAIL_WHERE = (
    "job_filing_number is not null AND ("
    "upper(floor_detail) like '%APT %' OR upper(floor_detail) like '%APT.%' OR "
    "upper(floor_detail) like '%APT#%' OR upper(floor_detail) like '%APARTMENT%' OR "
    "upper(floor_detail) like '%RESIDENTIAL UNIT%' OR "
    "upper(floor_detail) like '%DWELLING UNIT%' OR "
    "upper(floor_detail) like '%UNIT %' OR upper(floor_detail) like '%UNIT#%' OR "
    "upper(floor_detail) like '%UNIT NO%' OR "
    "upper(item_detail) like '%APT %' OR upper(item_detail) like '%APT.%' OR "
    "upper(item_detail) like '%APT#%' OR upper(item_detail) like '%APARTMENT%' OR "
    "upper(item_detail) like '%RESIDENTIAL UNIT%' OR "
    "upper(item_detail) like '%DWELLING UNIT%' OR "
    "upper(item_detail) like '%UNIT %' OR upper(item_detail) like '%UNIT#%' OR "
    "upper(item_detail) like '%UNIT NO%')"
)
_PLAIN_UNIT = re.compile(
    r"\bUNIT\b\s*(?:(?:NO|NUMBER)\.?\s*|#\s*)?([A-Z]{0,3}\d{1,4}[A-Z]{0,4}(?:[/-][A-Z0-9]+)*)\b",
    re.IGNORECASE,
)
_PLAIN_LETTER_UNIT = re.compile(
    r"\b(?i:UNIT)\b\s*(?:(?i:NO|NUMBER)\.?\s*|#\s*)?([A-Z]{1,3})\b"
)
_PLAIN_LETTER_STOP = {"AC", "AND", "FOR", "IN", "OF", "ON", "ONLY", "THE", "TO"}
_LETTER_APARTMENT = re.compile(
    r"\b(?:APT\.?|APARTMENT)\s+(?:(?:NO|NUMBER)\.?\s*|#\s*)?([A-Z])\b",
    re.IGNORECASE,
)
_LETTER_APARTMENT_LIST = re.compile(
    r"\b(?:APT\.?|APARTMENT)\s+([A-Z])\s+(?:AND|&|,)\s*([A-Z])\b",
    re.IGNORECASE,
)
_UNSEPARATED_LABEL_LIST = re.compile(
    r"\b(?:APTS?\.?|APARTMENTS?)\s*(?:(?:NO|NOS)\.?\s*|#\s*)?"
    r"((?:[A-Z]?\d+[A-Z]?\s+){1,29}[A-Z]?\d+[A-Z]?)\b",
    re.IGNORECASE,
)
_SPACED_SUFFIX = re.compile(
    r"\b(?i:APT\.?|APARTMENT)\s*(?:(?i:NO|NUMBER)\.?\s*|#\s*)?"
    r"(\d+)\s+([A-Z]{2,3})\b"
)
_TRAILING_APARTMENTS = re.compile(r"\b(?:APTS\.?|APARTMENTS)\b", re.IGNORECASE)
_COMPACT_SUFFIXED = re.compile(r"\b[A-Z]?\d+[A-Z]\b", re.IGNORECASE)
_COMPACT_LABEL = re.compile(r"\b[A-Z]?\d+[A-Z]?\b", re.IGNORECASE)
_LIST_SEPARATOR = re.compile(r"\s*(?:,|\.|;|&|/|\bAND\b)\s*", re.IGNORECASE)
_TRAILING_ACTION = re.compile(r"(?:\b(?:REWIRE|WIRE|WIRING)\b\s*){1,2}$", re.IGNORECASE)
_SAFE_LABEL = re.compile(r"(?:[A-Z]{0,3}\d{1,4}[A-Z]{0,4}|[A-Z]{1,3})", re.IGNORECASE)
_GLUED_NUMERIC_LABEL = re.compile(r"\d+[A-Z]+", re.IGNORECASE)
_VOLTAGE_LABEL = re.compile(r"\d{2,4}V", re.IGNORECASE)


def normalize_bbl(value):
    digits = "".join(char for char in str(value or "") if char.isdigit())
    return digits if len(digits) == 10 and digits[0] in "12345" else ""


def observed_date(value):
    text = str(value or "")[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return ""


def extract_electrical_detail_labels(text):
    """Extract explicit homes while rejecting generic electrical equipment units."""
    text = str(text or "")
    labels = extract_explicit_unit_labels(text)
    for match in _PLAIN_UNIT.finditer(text):
        labels.extend(extract_explicit_unit_labels(f"Apartment {match.group(1)}"))
    labels.extend(
        match.group(1) for match in _PLAIN_LETTER_UNIT.finditer(text)
        if match.group(1) not in _PLAIN_LETTER_STOP
    )
    labels.extend(match.group(1).upper() for match in _LETTER_APARTMENT.finditer(text))
    for match in _LETTER_APARTMENT_LIST.finditer(text):
        labels.extend((match.group(1).upper(), match.group(2).upper()))
    for match in _UNSEPARATED_LABEL_LIST.finditer(text):
        labels.extend(label.upper() for label in _COMPACT_LABEL.findall(match.group(1)))
    for match in _SPACED_SUFFIX.finditer(text):
        labels = [label for label in labels if re.sub(r"\s+", "", label) != match.group(1)]
        labels.append((match.group(1) + match.group(2)).upper())
    for marker in _TRAILING_APARTMENTS.finditer(text):
        prefix = text[max(0, marker.start() - 160):marker.start()]
        prefix = _TRAILING_ACTION.sub("", prefix)
        matches = list(_COMPACT_SUFFIXED.finditer(prefix))
        if not matches or prefix[matches[-1].end():].strip(" ,.;/&#"):
            continue
        trailing = [matches[-1].group(0)]
        for previous, current in zip(reversed(matches[:-1]), reversed(matches[1:])):
            if not _LIST_SEPARATOR.fullmatch(prefix[previous.end():current.start()]):
                break
            trailing.append(previous.group(0))
        labels.extend(label.upper() for label in reversed(trailing))
    cleaned = []
    for label in labels:
        compact = re.sub(r"\s+", "", label).upper()
        glued = _GLUED_NUMERIC_LABEL.findall(compact)
        if len(glued) > 1 and "".join(glued) == compact:
            cleaned.extend(part for part in glued if _SAFE_LABEL.fullmatch(part))
        elif _SAFE_LABEL.fullmatch(compact) and not _VOLTAGE_LABEL.fullmatch(compact):
            cleaned.append(compact)
    return list(dict.fromkeys(cleaned))


def request_rows(api, fields, where, order, offset, limit):
    params = urlencode({
        "$select": fields, "$where": where, "$order": order,
        "$limit": limit, "$offset": offset,
    })
    request = Request(f"{api}?{params}", headers={"User-Agent": "pricefixed-public-records/1.0"})
    with urlopen(request, timeout=180) as response:
        return json.loads(response.read())


def query_parent(offset, limit):
    return request_rows(
        PARENT_API,
        "job_filing_number,gis_bbl,filing_date,house_number,street_name",
        "gis_bbl is not null", "job_filing_number", offset, limit,
    )


def query_details(offset, limit):
    return request_rows(
        DETAIL_API,
        "unique_id,job_filing_number,floor_name,from_floor,to_floor,floor_detail,item,item_detail",
        DETAIL_WHERE, "unique_id", offset, limit,
    )


def save_progress(connection, source, offset, complete):
    connection.execute(
        "INSERT INTO progress(source,offset,complete,updated_at) VALUES (?,?,?,datetime('now')) "
        "ON CONFLICT(source) DO UPDATE SET offset=excluded.offset,"
        "complete=excluded.complete,updated_at=excluded.updated_at",
        (source, offset, complete),
    )


def mine_parents(connection, batch_size, page_limit):
    source = "dob_electrical_detail_parents"
    state = connection.execute(
        "SELECT offset,complete FROM progress WHERE source=?", (source,)
    ).fetchone()
    offset = state[0] if state else 0
    if state and state[1]:
        return
    pages = 0
    while True:
        rows = query_parent(offset, batch_size)
        output = []
        for row in rows:
            address = " ".join(
                str(row.get(field) or "").strip().upper()
                for field in ("house_number", "street_name") if row.get(field)
            )
            output.append((
                str(row.get("job_filing_number") or ""), normalize_bbl(row.get("gis_bbl")),
                address, observed_date(row.get("filing_date")),
            ))
        connection.executemany(
            "INSERT OR REPLACE INTO parent_jobs(job_filing_number,bbl,address,filing_date) "
            "VALUES (?,?,?,?)", output,
        )
        offset += len(rows)
        complete = int(len(rows) < batch_size)
        save_progress(connection, source, offset, complete)
        connection.commit()
        print(f"parent_offset={offset}", flush=True)
        if complete:
            return
        pages += 1
        if page_limit is not None and pages >= page_limit:
            return
        time.sleep(0.25)


def detail_text(row):
    parts = []
    floor = str(row.get("floor_detail") or "").strip()
    item = str(row.get("item_detail") or "").strip()
    if floor:
        parts.append(f"Floor detail: {floor}")
    if item and item not in {"''", '""'}:
        parts.append(f"Item detail: {item}")
    return "\n".join(parts)


def mine_details(connection, batch_size, page_limit):
    source = "dob_electrical_details_v3"
    state = connection.execute(
        "SELECT offset,complete FROM progress WHERE source=?", (source,)
    ).fetchone()
    offset = state[0] if state else 0
    if state and state[1]:
        print("DOB electrical detail mining already complete")
        return
    pages = 0
    while True:
        rows = query_details(offset, batch_size)
        output = []
        for row in rows:
            filing = str(row.get("job_filing_number") or "")
            parent = connection.execute(
                "SELECT bbl,address,filing_date FROM parent_jobs WHERE job_filing_number=?",
                (filing,),
            ).fetchone()
            text = detail_text(row)
            labels = extract_electrical_detail_labels(text)
            source_ref = str(row.get("unique_id") or "").strip()
            if not source_ref:
                continue
            bbl, address, filing_date = parent if parent else ("", "", "")
            status = "explicit_candidate" if parent and bbl and labels else (
                "missing_parent" if not parent or not bbl else "ambiguous_unit_word"
            )
            output.append((
                source_ref, bbl, address, "", text, filing_date,
                json.dumps(labels), status,
            ))
        connection.executemany(
            "INSERT OR REPLACE INTO descriptions "
            "(job_filing_number,bbl,address,zipcode,description,filing_date,extracted_labels,status) "
            "VALUES (?,?,?,?,?,?,?,?)", output,
        )
        offset += len(rows)
        complete = int(len(rows) < batch_size)
        save_progress(connection, source, offset, complete)
        connection.commit()
        explicit = connection.execute(
            "SELECT COUNT(*) FROM descriptions WHERE status='explicit_candidate'"
        ).fetchone()[0]
        print(f"detail_offset={offset} explicit_candidates={explicit}", flush=True)
        if complete:
            return
        pages += 1
        if page_limit is not None and pages >= page_limit:
            return
        time.sleep(0.25)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--batch-size", type=int, default=25000)
    parser.add_argument("--pages", type=int)
    args = parser.parse_args()
    if args.batch_size <= 0 or (args.pages is not None and args.pages <= 0):
        sys.exit("--batch-size and --pages must be positive")
    connection = sqlite3.connect(args.db)
    connection.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS parent_jobs (
            job_filing_number TEXT PRIMARY KEY, bbl TEXT NOT NULL,
            address TEXT NOT NULL, filing_date TEXT NOT NULL
        );
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
    mine_parents(connection, args.batch_size, args.pages)
    parent_complete = connection.execute(
        "SELECT complete FROM progress WHERE source='dob_electrical_detail_parents'"
    ).fetchone()
    if parent_complete and parent_complete[0] == 1:
        mine_details(connection, args.batch_size, args.pages)
    connection.close()


if __name__ == "__main__":
    main()
