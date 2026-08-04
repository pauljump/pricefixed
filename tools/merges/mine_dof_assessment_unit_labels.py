#!/usr/bin/env python3
"""Audit current DOF assessment apartment labels against official condo unit lots."""
import argparse
import csv
import json
import re
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.engine.dedupe import normalize_unit


DATASET = "8y4t-faws"
API = f"https://data.cityofnewyork.us/resource/{DATASET}.json"
RESIDENTIAL_TAX_CLASSES = {"1", "1A", "1B", "1C", "1D", "2", "2A", "2B", "2C"}


def usable_label(value):
    label = str(value or "").strip().upper()
    normalized = normalize_unit(label)
    if not normalized or len(normalized) > 12 or not any(char.isdigit() for char in normalized):
        return ""
    if label in {"`", "N/A", "NA", "NONE", "UNKNOWN"}:
        return ""
    if re.search(r"\b(?:GARAGE|PARKING|STORAGE|COMM|RETAIL|OFFICE)\b", label):
        return ""
    return normalized


def query(year, period, offset, limit):
    fields = "parid,aptno,curtaxclass,bldg_class,year,period,housenum_lo,street_name"
    classes = ",".join(f"'{value}'" for value in sorted(RESIDENTIAL_TAX_CLASSES))
    where = (
        f"year='{year}' AND period='{period}' AND curtaxclass in ({classes}) AND "
        "aptno is not null AND aptno!='' AND aptno!='`'"
    )
    params = urlencode({
        "$select": fields, "$where": where, "$order": "parid",
        "$limit": limit, "$offset": offset,
    })
    request = Request(f"{API}?{params}", headers={"User-Agent": "pricefixed-public-records/1.0"})
    with urlopen(request, timeout=180) as response:
        return json.loads(response.read())


def collect(stage, year, period, batch_size, pages=None):
    connection = sqlite3.connect(stage)
    connection.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS assessment_units (
            parid TEXT PRIMARY KEY, aptno TEXT NOT NULL, tax_class TEXT,
            building_class TEXT, assessment_year TEXT NOT NULL,
            assessment_period TEXT NOT NULL, address TEXT
        );
        CREATE TABLE IF NOT EXISTS progress (
            source TEXT PRIMARY KEY, offset INTEGER NOT NULL, complete INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)
    source = f"dof_assessment_units_{year}_{period}"
    state = connection.execute("SELECT offset,complete FROM progress WHERE source=?", (source,)).fetchone()
    offset = state[0] if state else 0
    if state and state[1]:
        connection.close()
        return
    completed_pages = 0
    while True:
        rows = query(year, period, offset, batch_size)
        output = []
        for row in rows:
            address = " ".join(
                str(row.get(field) or "").strip().upper()
                for field in ("housenum_lo", "street_name") if row.get(field)
            )
            output.append((
                str(row.get("parid") or ""), str(row.get("aptno") or "").strip(),
                str(row.get("curtaxclass") or ""), str(row.get("bldg_class") or ""),
                str(row.get("year") or year), str(row.get("period") or period), address,
            ))
        connection.executemany(
            "INSERT OR REPLACE INTO assessment_units "
            "(parid,aptno,tax_class,building_class,assessment_year,assessment_period,address) "
            "VALUES (?,?,?,?,?,?,?)", output,
        )
        offset += len(rows)
        complete = int(len(rows) < batch_size)
        connection.execute(
            "INSERT INTO progress(source,offset,complete,updated_at) VALUES (?,?,?,datetime('now')) "
            "ON CONFLICT(source) DO UPDATE SET offset=excluded.offset,complete=excluded.complete,updated_at=excluded.updated_at",
            (source, offset, complete),
        )
        connection.commit()
        print(f"offset={offset}", flush=True)
        if complete:
            break
        completed_pages += 1
        if pages is not None and completed_pages >= pages:
            break
        time.sleep(0.25)
    connection.close()


def classify(stage, catalog_path, accepted_path, rejected_path, summary_path, year, period):
    stage_db = sqlite3.connect(f"file:{Path(stage).resolve()}?mode=ro", uri=True)
    state = stage_db.execute(
        "SELECT complete FROM progress WHERE source=?", (f"dof_assessment_units_{year}_{period}",)
    ).fetchone()
    if not state or state[0] != 1:
        raise SystemExit("DOF assessment unit mining is incomplete")
    catalog = sqlite3.connect(f"file:{Path(catalog_path).resolve()}?mode=ro", uri=True)
    official = {
        row[0]: (row[1] or "")
        for row in catalog.execute("SELECT unit_lot_bbl,unit_designation FROM official_unit_lots")
    }
    existing = {
        (row[0], row[1]) for row in catalog.execute("SELECT bbl,normalized_unit FROM units")
        if row[0] in official
    }
    stamp = datetime.now(timezone.utc).date().isoformat()
    accepted = []
    rejected = []
    reasons = Counter()
    for parid, aptno, tax_class, building_class, assessment_year, assessment_period, address in stage_db.execute(
        "SELECT parid,aptno,tax_class,building_class,assessment_year,assessment_period,address "
        "FROM assessment_units ORDER BY parid"
    ):
        normalized = usable_label(aptno)
        designation = official.get(parid)
        official_normalized = normalize_unit(designation) if designation else ""
        reason = ""
        if parid not in official:
            reason = "not_official_condo_unit_lot"
        elif tax_class not in RESIDENTIAL_TAX_CLASSES:
            reason = "not_residential_tax_class"
        elif not normalized:
            reason = "unusable_assessment_label"
        elif official_normalized and normalized != official_normalized:
            reason = "conflicts_with_condo_designation"
        elif (parid, normalized) in existing:
            reason = "already_in_catalog"
        if reason:
            reasons[reason] += 1
            rejected.append((parid, aptno, designation or "", reason))
            continue
        source_ref = f"{parid}:{assessment_year}:{assessment_period}"
        source_url = f"{API}?" + urlencode({
            "$select": "parid,aptno,curtaxclass,bldg_class,year,period,housenum_lo,street_name",
            "$where": f"parid='{parid}' AND year='{assessment_year}' AND period='{assessment_period}'",
        })
        accepted.append((
            parid, aptno, normalized, address, tax_class, building_class,
            assessment_year, assessment_period, source_ref, source_url, stamp,
            "matches_condo_designation" if official_normalized else "fills_blank_condo_designation",
        ))
    stage_db.close()
    catalog.close()
    accepted_path = Path(accepted_path)
    accepted_path.parent.mkdir(parents=True, exist_ok=True)
    with accepted_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("unit_lot_bbl", "unit_label", "normalized_unit", "address", "tax_class",
                         "building_class", "assessment_year", "assessment_period", "source_ref",
                         "source_url", "observed_at", "basis"))
        writer.writerows(accepted)
    with Path(rejected_path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("unit_lot_bbl", "assessment_unit_label", "condo_unit_designation", "reason"))
        writer.writerows(rejected)
    summary = {
        "dataset": DATASET, "assessment_year": year, "assessment_period": period,
        "stage_rows": len(accepted) + len(rejected), "net_new_candidates": len(accepted),
        "rejection_reasons": dict(sorted(reasons.items())), "catalog_writes": 0,
    }
    Path(summary_path).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="resumable compact staging database")
    parser.add_argument("--catalog-db", required=True)
    parser.add_argument("--accepted", required=True)
    parser.add_argument("--rejected", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--year", default="2027")
    parser.add_argument("--period", default="3")
    parser.add_argument("--batch-size", type=int, default=50000)
    parser.add_argument("--pages", type=int)
    args = parser.parse_args()
    if args.batch_size <= 0 or (args.pages is not None and args.pages <= 0):
        sys.exit("--batch-size and --pages must be positive")
    collect(args.db, args.year, args.period, args.batch_size, args.pages)
    classify(args.db, args.catalog_db, args.accepted, args.rejected, args.summary, args.year, args.period)


if __name__ == "__main__":
    main()
