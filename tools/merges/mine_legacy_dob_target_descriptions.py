#!/usr/bin/env python3
"""Refresh exact-address legacy DOB descriptions for a bounded target queue.

This is a source-refresh companion to ``mine_legacy_dob_description_units.py``.
It queries the legacy DOB corpus by BBL, then joins rows back to the target by
the source address after the project's conservative address normalization.  A
BBL match alone is never enough.  Empty targets are retained as
``no_exact_source_rows`` so a negative result is auditable and repeatable.

The output is evidence preparation only.  It does not write the catalog.
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


API = "https://data.cityofnewyork.us/resource/ic3t-wcy2.json"
SELECT = (
    "job_s1_no,bbl,house__,street_name,job_description,latest_action_date"
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
    params = urlencode({
        "$select": SELECT,
        "$where": f"bbl='{bbl}'",
        "$order": "job_s1_no DESC",
        "$limit": limit,
    })
    source_url = f"{API}?{params}"
    request = Request(source_url, headers={"User-Agent": "pricefixed-public-records/1.0"})
    with urlopen(request, timeout=180) as response:
        rows = json.loads(response.read())
    if isinstance(rows, dict) and rows.get("error"):
        raise RuntimeError(rows.get("message", "legacy DOB query failed"))
    return rows, source_url


def _base(target, bbl, source_url, source_address="", source_ref="", observed_at="",
          evidence="", status=""):
    return {
        "property": target.get("property", ""),
        "target_address": target["target_address"],
        "normalized_address": target["normalized_address"],
        "bbl": bbl,
        "source_address": source_address,
        "unit_label": "",
        "source_ref": source_ref,
        "observed_at": observed_at,
        "source_url": source_url,
        "evidence": evidence,
        "status": status,
    }


def collect(target_rows, fetch=query_bbl):
    targets = {}
    output = []
    for target in target_rows:
        bbl = _target_bbl(target)
        address = _target_address(target)
        normalized = normalize_address(address)
        prepared = {
            **target,
            "bbl": bbl,
            "target_address": address,
            "normalized_address": normalized,
        }
        if bbl and normalized:
            targets.setdefault((bbl, normalized), []).append(prepared)
        else:
            output.append(_base(prepared, bbl, "", status="unparseable_target"))

    for bbl in sorted({key[0] for key in targets}):
        try:
            rows, source_url = fetch(bbl)
        except Exception as exc:
            for (target_bbl, _), values in targets.items():
                if target_bbl != bbl:
                    continue
                for target in values:
                    output.append(_base(
                        target, bbl, "", status=f"error:{type(exc).__name__}"
                    ))
            continue

        matched_keys = set()
        for row in rows:
            source_address = " ".join(
                str(row.get(field) or "").strip()
                for field in ("house__", "street_name")
                if row.get(field)
            )
            key = (bbl, normalize_address(source_address))
            matched_targets = targets.get(key, [])
            if not matched_targets:
                continue
            matched_keys.add(key)
            description = str(row.get("job_description") or "").strip()
            labels = extract_explicit_unit_labels(description)
            status = "explicit_candidate" if labels else (
                "ambiguous_description" if description else "no_unit_description"
            )
            for target in matched_targets:
                for label in labels or [""]:
                    record = _base(
                        target, bbl, source_url, source_address,
                        str(row.get("job_s1_no") or ""),
                        str(row.get("latest_action_date") or ""),
                        description, status,
                    )
                    record["unit_label"] = label
                    output.append(record)

        for key, values in targets.items():
            if key[0] != bbl or key in matched_keys:
                continue
            for target in values:
                output.append(_base(target, bbl, source_url, status="no_exact_source_rows"))

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
    print(f"wrote {len(rows)} legacy DOB target observations to {output}")


if __name__ == "__main__":
    main()
