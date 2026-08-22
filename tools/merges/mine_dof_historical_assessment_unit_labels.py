#!/usr/bin/env python3
"""Audit historical DOF assessment labels against today's official condo unit lots."""
import argparse
import csv
import json
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.engine.dedupe import normalize_unit
from tools.merges.mine_dof_assessment_unit_labels import RESIDENTIAL_TAX_CLASSES, usable_label


DATASET = "kevu-8hby"
API = f"https://data.cityofnewyork.us/resource/{DATASET}.json"


def dataset_api(dataset):
    return f"https://data.cityofnewyork.us/resource/{dataset}.json"


def progress_source(dataset, year):
    if dataset == DATASET:
        return f"dof_historical_assessment_units_{year}"
    return f"dof_historical_assessment_units_{dataset}_{year}"


def house_number(value):
    parts = str(value or "").strip().split("-", 1)
    normalized = [part.lstrip("0") or "0" for part in parts]
    return "-".join(normalized)


def query(year, offset, limit, dataset=DATASET):
    fields = "bble,aptno,txcl,bldgcl,year4,hnum_lo,str_name,zip"
    classes = ",".join(f"'{value}'" for value in sorted(RESIDENTIAL_TAX_CLASSES))
    where = (
        f"year4='{year}' AND res_unit=1 AND txcl in ({classes}) AND "
        "aptno is not null AND trim(aptno)!=''"
    )
    params = urlencode({
        "$select": fields, "$where": where, "$order": "bble",
        "$limit": limit, "$offset": offset,
    })
    request = Request(
        f"{dataset_api(dataset)}?{params}",
        headers={"User-Agent": "pricefixed-public-records/1.0"},
    )
    with urlopen(request, timeout=180) as response:
        return json.loads(response.read())


def collect(stage, year, batch_size, pages=None, dataset=DATASET):
    connection = sqlite3.connect(stage)
    connection.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS assessment_units (
            parid TEXT PRIMARY KEY, aptno TEXT NOT NULL, tax_class TEXT,
            building_class TEXT, assessment_year TEXT NOT NULL, address TEXT, zipcode TEXT
        );
        CREATE TABLE IF NOT EXISTS progress (
            source TEXT PRIMARY KEY, offset INTEGER NOT NULL, complete INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)
    source = progress_source(dataset, year)
    state = connection.execute("SELECT offset,complete FROM progress WHERE source=?", (source,)).fetchone()
    offset = state[0] if state else 0
    if state and state[1]:
        connection.close()
        return
    completed_pages = 0
    while True:
        rows = query(year, offset, batch_size, dataset)
        output = []
        for row in rows:
            address = " ".join(part for part in (
                house_number(row.get("hnum_lo")),
                str(row.get("str_name") or "").strip().upper(),
            ) if part)
            output.append((
                str(row.get("bble") or ""), str(row.get("aptno") or "").strip(),
                str(row.get("txcl") or ""), str(row.get("bldgcl") or ""),
                str(row.get("year4") or year), address, str(row.get("zip") or ""),
            ))
        connection.executemany(
            "INSERT OR REPLACE INTO assessment_units "
            "(parid,aptno,tax_class,building_class,assessment_year,address,zipcode) "
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


def classify(
    stage, catalog_path, accepted_path, rejected_path, summary_path, year, dataset=DATASET
):
    stage_db = sqlite3.connect(f"file:{Path(stage).resolve()}?mode=ro", uri=True)
    state = stage_db.execute(
        "SELECT complete FROM progress WHERE source=?", (progress_source(dataset, year),)
    ).fetchone()
    if not state or state[0] != 1:
        raise SystemExit("historical DOF assessment mining is incomplete")
    catalog = sqlite3.connect(f"file:{Path(catalog_path).resolve()}?mode=ro", uri=True)
    official = {
        row[0]: (row[1] or "")
        for row in catalog.execute("SELECT unit_lot_bbl,unit_designation FROM official_unit_lots")
    }
    existing_bbls = {
        row[0] for row in catalog.execute("SELECT DISTINCT bbl FROM units") if row[0] in official
    }
    accepted = []
    rejected = []
    reasons = Counter()
    rows = stage_db.execute(
        "SELECT parid,aptno,tax_class,building_class,assessment_year,address,zipcode "
        "FROM assessment_units ORDER BY parid"
    )
    for parid, aptno, tax_class, building_class, assessment_year, address, zipcode in rows:
        normalized = usable_label(aptno)
        designation = official.get(parid)
        official_normalized = normalize_unit(designation) if designation else ""
        reason = ""
        if parid not in official:
            reason = "not_current_official_condo_unit_lot"
        elif tax_class not in RESIDENTIAL_TAX_CLASSES:
            reason = "not_residential_tax_class"
        elif not normalized:
            reason = "unusable_assessment_label"
        elif parid in existing_bbls:
            reason = "official_unit_lot_already_has_unit"
        elif official_normalized:
            # Current official designations are stronger than this historical
            # snapshot. Do not reintroduce unit lots removed by later evidence.
            reason = "official_designation_already_present"
        if reason:
            reasons[reason] += 1
            rejected.append((parid, aptno, designation or "", reason))
            continue
        source_ref = f"{parid}:{assessment_year}"
        source_url = f"{dataset_api(dataset)}?" + urlencode({
            "$select": "bble,aptno,txcl,bldgcl,year4,hnum_lo,str_name,zip",
            "$where": f"bble='{parid}' AND year4='{assessment_year}'",
        })
        accepted.append((
            parid, aptno, normalized, address, tax_class, building_class,
            assessment_year, "historical", source_ref, source_url,
            f"{assessment_year}-01-01", "fills_blank_condo_designation",
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
        "dataset": dataset, "assessment_year": year,
        "stage_rows": len(accepted) + len(rejected), "net_new_candidates": len(accepted),
        "rejection_reasons": dict(sorted(reasons.items())), "catalog_writes": 0,
    }
    Path(summary_path).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--catalog-db", required=True)
    parser.add_argument("--accepted", required=True)
    parser.add_argument("--rejected", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--year", default="2017")
    parser.add_argument("--dataset", default=DATASET)
    parser.add_argument("--batch-size", type=int, default=50000)
    parser.add_argument("--pages", type=int)
    args = parser.parse_args()
    if args.batch_size <= 0 or (args.pages is not None and args.pages <= 0):
        sys.exit("--batch-size and --pages must be positive")
    collect(args.db, args.year, args.batch_size, args.pages, args.dataset)
    classify(
        args.db, args.catalog_db, args.accepted, args.rejected, args.summary,
        args.year, args.dataset,
    )


if __name__ == "__main__":
    main()
