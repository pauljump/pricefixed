#!/usr/bin/env python3
"""Verify omitted dwelling/residential-unit marker rows with local Qwen."""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


QUEUES = (
    ("dcp", "br6q-ssj3", "job_number", "dcp_housing_project_description_delta",
     "dcp_housing_project_description_units"),
    ("approved_permit", "rbx6-tga4", "work_permit", "dob_approved_permit_description_delta",
     "dob_approved_permit_description_units"),
    ("electrical", "dm9a-ab7w", "job_filing_number", "dob_electrical_description_delta",
     "dob_electrical_permit_description_units"),
    ("dob_violation", "3h2n-5cm9", "isn_dob_bis_viol", "dob_violation_description_delta",
     "dob_violation_description_units"),
    ("ecb", "6bgk-3dad", "ecb_violation_number", "dob_ecb_description_delta",
     "dob_ecb_violation_description_units"),
    ("oath", "jz4z-kudi", "ticket_number", "oath_dob_description_delta",
     "oath_dob_violation_description_units"),
)


def run(*parts):
    print("running:", " ".join(str(part) for part in parts), flush=True)
    subprocess.run([str(part) for part in parts], check=True)


def wait_for_pid(pid):
    while True:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(60)


def process_queue(root, python, work, catalog, config):
    source, dataset, id_field, source_type, catalog_source = config
    stem = f"dwelling-unit-marker-delta-{source}"
    database = work / f"{stem}.db"
    run(python, root / "tools/merges/mine_dwelling_unit_description_delta.py",
        "--source", source, "--db", database)
    run(python, root / "tools/local_model/export_dob_description_packets.py",
        "--descriptions-db", database, "--catalog-db", catalog,
        "--output", work / f"{stem}-packets.jsonl",
        "--progress-source", f"dwelling_unit_marker_delta_{source}",
        "--dataset", dataset, "--id-field", id_field, "--packet-prefix", stem,
        "--source-type", source_type)
    run(python, root / "tools/local_model/run_qwen_extraction.py",
        "--input", work / f"{stem}-packets.jsonl",
        "--output", work / f"{stem}-results.jsonl", "--batch-size", "8")
    run(python, root / "tools/local_model/prepare_dob_description_results.py",
        "--packets", work / f"{stem}-packets.jsonl",
        "--results", work / f"{stem}-results.jsonl",
        "--accepted", work / f"{stem}-accepted.csv",
        "--rejected", work / f"{stem}-rejected.csv",
        "--summary", work / f"{stem}-summary.json")
    merge_summary = work / f"{stem}-merge-summary.json"
    run(python, root / "tools/merges/merge_dob_description_results.py",
        "--csv", work / f"{stem}-accepted.csv", "--catalog-db", catalog,
        "--summary", merge_summary, "--source", catalog_source,
        "--methodology", "Explicit dwelling-unit or residential-unit label in an official agency description omitted by the earlier apt-only source filter; deterministically parsed, reviewed by local Qwen, and retained with verbatim evidence",
        "--match-rationale", "The original agency record supplies the BBL and verbatim unit-label evidence",
        "--apply")
    return json.loads(merge_summary.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-pipeline-pid", type=int, required=True)
    parser.add_argument("--catalog-db", required=True)
    parser.add_argument("--work-dir", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    work = Path(args.work_dir)
    wait_for_pid(args.base_pipeline_pid)
    summaries = [
        process_queue(root, sys.executable, work, Path(args.catalog_db), config)
        for config in QUEUES
    ]
    aggregate = {
        "catalog_writes": 1,
        "queues": len(summaries),
        "net_new_units": sum(summary.get("net_new_units", 0) for summary in summaries),
        "verified_unique_units": sum(
            summary.get("verified_unique_units", 0) for summary in summaries
        ),
    }
    path = work / "dwelling-unit-marker-delta-merge-summary.json"
    path.write_text(json.dumps(aggregate, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(aggregate, indent=2))


if __name__ == "__main__":
    main()
