#!/usr/bin/env python3
"""Verify a Pricefixed public release bundle without opening the source catalog."""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path


def _load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read {path.name}: {error}") from error


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _csv_rows_and_values(path, value_column=None):
    rows = 0
    values = set()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"missing CSV header: {path.name}")
        if value_column and value_column not in reader.fieldnames:
            raise ValueError(f"missing {value_column} column: {path.name}")
        for row in reader:
            rows += 1
            if value_column:
                values.add(row[value_column])
    return rows, values


def verify_release(release):
    manifest = _load_json(release / "manifest.json")
    report = _load_json(release / "quality-report.json")
    policy_path = release / "source-policy.json"
    policy = _load_json(policy_path)
    policy_metadata = manifest.get("source_policy", {})
    if policy_metadata.get("policy_id") != policy.get("policy_id"):
        raise ValueError("source policy ID differs from manifest")
    if report.get("source_policy", {}).get("policy_id") != policy.get("policy_id"):
        raise ValueError("source policy ID differs from quality report")
    if _sha256(policy_path) != policy_metadata.get("sha256"):
        raise ValueError("checksum mismatch: source-policy.json")

    observed_rows = {}
    for name, metadata in manifest.get("files", {}).items():
        path = release / name
        if not path.is_file():
            raise ValueError(f"missing release file: {name}")
        if _sha256(path) != metadata.get("sha256"):
            raise ValueError(f"checksum mismatch: {name}")
        rows, _ = _csv_rows_and_values(path)
        if rows != metadata.get("rows"):
            raise ValueError(f"row count mismatch: {name}")
        observed_rows[name] = rows

    allowed = set(policy.get("included_sources", []))
    _, exported_sources = _csv_rows_and_values(release / "sources.csv", "source")
    _, observation_sources = _csv_rows_and_values(release / "unit_observations.csv", "source")
    if not exported_sources <= allowed:
        raise ValueError(f"sources outside release policy: {sorted(exported_sources - allowed)}")
    if not observation_sources <= exported_sources:
        raise ValueError(f"observation sources missing from sources.csv: {sorted(observation_sources - exported_sources)}")
    if observed_rows.get("units.csv") != report.get("counts", {}).get("units"):
        raise ValueError("unit count differs between manifest and quality report")
    if observed_rows.get("unit_observations.csv") != report.get("counts", {}).get("resolved_unit_observations"):
        raise ValueError("observation count differs between manifest and quality report")
    return {
        "release_units": observed_rows.get("units.csv", 0),
        "release_observations": observed_rows.get("unit_observations.csv", 0),
        "withheld_units": report.get("local_catalog_counts", {}).get("units_withheld_by_source_policy"),
        "exported_sources": len(exported_sources),
        "policy_id": policy.get("policy_id"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release", help="directory containing an exported release bundle")
    args = parser.parse_args()
    release = Path(args.release)
    if not release.is_dir():
        sys.exit(f"release directory not found: {release}")
    try:
        result = verify_release(release)
    except ValueError as error:
        sys.exit(str(error))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
