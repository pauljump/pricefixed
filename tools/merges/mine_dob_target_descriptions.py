#!/usr/bin/env python3
"""Collect exact-address DOB job-description unit evidence for ranked targets.

This is a bounded source pass, not a roster generator. It retains the verbatim
official job description and emits an explicit unit candidate only when the
description parser finds a label attached to an apartment/unit marker and the
DOB address exactly matches a queued target address on the same BBL.
"""
import argparse
import csv
import json
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.engine.crosswalk import normalize_address
from pricefixed.engine.identifiers import normalize_bbl
from pricefixed.engine.unit_mentions import extract_explicit_unit_labels


API = "https://data.cityofnewyork.us/resource/w9ak-ipjd.json"
SELECT = (
    "job_filing_number,bbl,house_no,street_name,postcode,job_description,filing_date"
)
MARKER_WHERE = (
    "(apt_condo_no_s IS NULL OR apt_condo_no_s='') AND job_description IS NOT NULL AND "
    "(upper(job_description) like '%APT%' OR upper(job_description) like '%APARTMENT%' "
    "OR upper(job_description) like '%UNIT%')"
)
FIELDS = (
    "property", "target_address", "normalized_address", "bbl", "source_address",
    "unit_label", "source_ref", "observed_at", "source_url", "evidence", "status",
)


def _target_bbl(row):
    return normalize_bbl(row.get("bbl") or row.get("resolved_bbl")) or ""


def _target_address(row):
    return row.get("address") or row.get("target_address") or ""


def query_bbl(bbl, limit=5000):
    where = f"bbl='{bbl}' AND {MARKER_WHERE}"
    params = urlencode({
        "$select": SELECT,
        "$where": where,
        "$order": "job_filing_number DESC",
        "$limit": limit,
    })
    source_url = f"{API}?{params}"
    request = Request(source_url, headers={"User-Agent": "pricefixed-public-records/1.0"})
    with urlopen(request, timeout=180) as response:
        rows = json.loads(response.read())
    if isinstance(rows, dict) and rows.get("error"):
        raise RuntimeError(rows.get("message", "DOB NOW query failed"))
    return rows, source_url


def collect(target_rows, fetch=query_bbl):
    targets = {}
    output = []
    for target in target_rows:
        bbl = _target_bbl(target)
        address = _target_address(target)
        normalized = normalize_address(address)
        if bbl and normalized:
            targets.setdefault((bbl, normalized), []).append({
                **target,
                "bbl": bbl,
                "target_address": address,
                "normalized_address": normalized,
            })
        else:
            output.append({
                "property": target.get("property", ""),
                "target_address": address,
                "normalized_address": normalized,
                "bbl": bbl,
                "source_address": "",
                "unit_label": "",
                "source_ref": "",
                "observed_at": "",
                "source_url": "",
                "evidence": "",
                "status": "unparseable_target",
            })

    for bbl in sorted({key[0] for key in targets}):
        try:
            rows, source_url = fetch(bbl)
        except Exception as exc:
            for target in [
                target for (target_bbl_value, _), values in targets.items()
                if target_bbl_value == bbl for target in values
            ]:
                output.append({
                    "property": target.get("property", ""),
                    "target_address": target["target_address"],
                    "normalized_address": target["normalized_address"],
                    "bbl": bbl,
                    "source_address": "",
                    "unit_label": "",
                    "source_ref": "",
                    "observed_at": "",
                    "source_url": "",
                    "evidence": "",
                    "status": f"error:{type(exc).__name__}",
                })
            continue
        for row in rows:
            source_address = " ".join(
                str(row.get(field) or "").strip()
                for field in ("house_no", "street_name")
                if row.get(field)
            )
            normalized_source = normalize_address(source_address)
            matched_targets = targets.get((bbl, normalized_source), [])
            if not matched_targets:
                continue
            description = str(row.get("job_description") or "").strip()
            labels = extract_explicit_unit_labels(description)
            status = "explicit_candidate" if labels else "ambiguous_description"
            for target in matched_targets:
                base = {
                    "property": target.get("property", ""),
                    "target_address": target["target_address"],
                    "normalized_address": target["normalized_address"],
                    "bbl": bbl,
                    "source_address": source_address,
                    "source_ref": str(row.get("job_filing_number") or ""),
                    "observed_at": str(row.get("filing_date") or ""),
                    "source_url": source_url,
                    "evidence": description,
                    "status": status,
                }
                for label in labels or [""]:
                    output.append({**base, "unit_label": label})
    output.sort(key=lambda row: (
        row["property"], row["target_address"], row["source_ref"], row["unit_label"]
    ))
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit-per-bbl", type=int, default=5000)
    args = parser.parse_args()
    if args.limit_per_bbl <= 0:
        sys.exit("--limit-per-bbl must be positive")
    with open(args.targets, encoding="utf-8", newline="") as handle:
        targets = list(csv.DictReader(handle))

    def fetch(bbl):
        return query_bbl(bbl, limit=args.limit_per_bbl)

    rows = collect(targets, fetch=fetch)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} exact-address DOB description observations to {output}")


if __name__ == "__main__":
    main()
