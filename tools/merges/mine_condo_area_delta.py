#!/usr/bin/env python3
"""Find residential unit lots present in CONDO_AREA but absent from the condo registry."""
import argparse
import csv
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.engine.crosswalk import normalize_address
from pricefixed.engine.dedupe import normalize_unit


DATASET = "b5bf-t8kd"
ACRIS_DATASET = "8h5j-fqxa"
API = f"https://data.cityofnewyork.us/resource/{DATASET}.json"
ACRIS_API = f"https://data.cityofnewyork.us/resource/{ACRIS_DATASET}.json"
FIELDS = (
    "objectid,base_bbl,unit_bbl,unit_lot,unit_designation,bin,condo_key,"
    "floor_text,floor_num,room_desc,model,last_edited_date"
)
_OFFICIAL_UNIT = re.compile(r"^(?:[A-Z]?\d[A-Z0-9]{0,6}|\d{1,4}[A-Z]{0,4}|PH[A-Z0-9]{0,3})$")
_NONHOME_PREFIX = re.compile(r"^(?:PK|PARK|STOR|GAR|COMM|RETAIL|OFFICE)")


def normalize_bbl(value):
    digits = "".join(char for char in str(value or "") if char.isdigit())
    return digits if len(digits) == 10 and digits[0] in "12345" else ""


def fetch_area_rows():
    params = urlencode({"$select": FIELDS, "$where": "unit_bbl is not null", "$limit": 5000})
    request = Request(f"{API}?{params}", headers={"User-Agent": "pricefixed-public-records/1.0"})
    with urlopen(request, timeout=180) as response:
        return json.loads(response.read())


def fetch_acris_rows(bbl):
    borough, block, lot = bbl[0], str(int(bbl[1:6])), str(int(bbl[6:]))
    fields = "document_id,borough,block,lot,property_type,street_number,street_name,unit"
    params = urlencode({
        "$select": fields,
        "$where": f"borough='{borough}' AND block='{block}' AND lot='{lot}'",
        "$limit": 5000,
    })
    request = Request(f"{ACRIS_API}?{params}", headers={"User-Agent": "pricefixed-public-records/1.0"})
    with urlopen(request, timeout=180) as response:
        return json.loads(response.read())


def residential_room(value):
    text = str(value or "").strip().upper()
    return any(token in text for token in ("STUDIO", "BED", "BATH", "APARTMENT"))


def official_unit_label(value):
    """Normalize an explicit DOF/ACRIS unit field without mistaking 4F for a floor."""
    normalized = normalize_unit(value)
    if not normalized or _NONHOME_PREFIX.match(normalized) or not _OFFICIAL_UNIT.fullmatch(normalized):
        return ""
    return normalized


def choose_label(row, acris_labels, existing_base_labels):
    """Return (label, basis, reason) using only mutually consistent official evidence."""
    bbl = normalize_bbl(row.get("unit_bbl"))
    base_bbl = normalize_bbl(row.get("base_bbl"))
    designation = str(row.get("unit_designation") or "").strip()
    normalized_designation = official_unit_label(designation)
    normalized_acris = sorted({
        official_unit_label(label) for label in acris_labels if official_unit_label(label)
    })
    if not bbl or not base_bbl:
        return "", "", "invalid_bbl"
    candidate = normalized_designation
    basis = "condo_area_designation"
    if not candidate:
        if designation.upper() != "UNIT" or not residential_room(row.get("room_desc")):
            return "", "", "no_residential_designation"
        if len(normalized_acris) != 1:
            return "", "", "generic_designation_without_unique_acris_label"
        candidate = normalized_acris[0]
        basis = "residential_geometry_plus_acris_label"
    elif normalized_acris and normalized_acris != [candidate]:
        return "", "", "acris_label_conflict"
    elif normalized_acris:
        basis = "matching_condo_area_and_acris_labels"
    lot_matches = str(row.get("unit_lot") or "").lstrip("0") == str(int(bbl[6:]))
    if not lot_matches and not normalized_acris:
        return "", "", "unit_lot_mismatch_without_acris_support"
    if (base_bbl, candidate) in existing_base_labels:
        return "", "", "duplicate_designation_in_condo"
    return candidate, basis, ""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-db", required=True)
    parser.add_argument("--accepted", required=True)
    parser.add_argument("--rejected", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()
    catalog = sqlite3.connect(f"file:{Path(args.catalog_db).resolve()}?mode=ro", uri=True)
    existing_bbls = {row[0] for row in catalog.execute("SELECT unit_lot_bbl FROM official_unit_lots")}
    existing_base_labels = {
        (base, normalize_unit(label))
        for base, label in catalog.execute(
            "SELECT condo_base_bbl,unit_designation FROM official_unit_lots "
            "WHERE condo_base_bbl IS NOT NULL AND unit_designation IS NOT NULL"
        ) if normalize_unit(label)
    }
    rows_by_bbl = defaultdict(list)
    for row in fetch_area_rows():
        rows_by_bbl[normalize_bbl(row.get("unit_bbl"))].append(row)
    accepted = []
    rejected = []
    reasons = Counter()
    for bbl, rows in sorted(rows_by_bbl.items()):
        if not bbl:
            reasons["invalid_bbl"] += 1
            continue
        if bbl in existing_bbls:
            reasons["already_in_condo_registry"] += 1
            continue
        signatures = {
            (row.get("base_bbl"), row.get("unit_designation"), row.get("unit_lot")) for row in rows
        }
        if len(signatures) != 1:
            reasons["conflicting_geometry_rows"] += 1
            rejected.append((bbl, "conflicting_geometry_rows", json.dumps(rows, sort_keys=True)))
            continue
        row = rows[0]
        acris_rows = fetch_acris_rows(bbl)
        labels = [item.get("unit") for item in acris_rows if item.get("unit")]
        label, basis, reason = choose_label(row, labels, existing_base_labels)
        if reason:
            reasons[reason] += 1
            rejected.append((bbl, reason, json.dumps({"area": row, "acris": acris_rows}, sort_keys=True)))
            continue
        address_pairs = {
            " ".join((str(item.get("street_number") or "").strip(),
                      " ".join(str(item.get("street_name") or "").split())))
            for item in acris_rows if item.get("street_number") and item.get("street_name")
        }
        normalized_addresses = {normalize_address(value) for value in address_pairs}
        address = sorted(address_pairs, key=lambda value: (len(value), value))[0] if (
            address_pairs and len(normalized_addresses) == 1
        ) else ""
        object_id = str(row.get("objectid") or "")
        area_url = f"{API}?" + urlencode({"$where": f"objectid='{object_id}'"})
        acris_url = f"{ACRIS_API}?" + urlencode({
            "$where": f"borough='{bbl[0]}' AND block='{int(bbl[1:6])}' AND lot='{int(bbl[6:])}'"
        })
        accepted.append({
            "unit_lot_bbl": bbl, "condo_base_bbl": normalize_bbl(row.get("base_bbl")),
            "unit_label": label, "normalized_unit": normalize_unit(label),
            "source_designation": str(row.get("unit_designation") or ""),
            "unit_lot": str(row.get("unit_lot") or ""), "condo_key": str(row.get("condo_key") or ""),
            "bin": str(row.get("bin") or ""), "floor_text": str(row.get("floor_text") or ""),
            "model": str(row.get("model") or ""), "room_desc": str(row.get("room_desc") or ""),
            "address": address, "object_id": object_id, "observed_at": str(row.get("last_edited_date") or "")[:10],
            "basis": basis, "source_url": area_url, "acris_source_url": acris_url,
        })
    catalog.close()
    fields = tuple(accepted[0]) if accepted else (
        "unit_lot_bbl", "condo_base_bbl", "unit_label", "normalized_unit", "source_designation",
        "unit_lot", "condo_key", "bin", "floor_text", "model", "room_desc", "address",
        "object_id", "observed_at", "basis", "source_url", "acris_source_url",
    )
    with Path(args.accepted).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(accepted)
    with Path(args.rejected).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("unit_lot_bbl", "reason", "evidence"))
        writer.writerows(rejected)
    summary = {
        "dataset": DATASET, "dataset_rows": sum(map(len, rows_by_bbl.values())),
        "unique_unit_bbls": len(rows_by_bbl), "net_new_candidates": len(accepted),
        "rejection_reasons": dict(sorted(reasons.items())), "catalog_writes": 0,
    }
    Path(args.summary).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
