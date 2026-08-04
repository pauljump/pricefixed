#!/usr/bin/env python3
"""Verify additional direct-BBL NYC agency descriptions with local Qwen."""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


QUEUES = (
    ("laa", "xxbr-ypig", "job_number,filing_number,permit_number",
     "dob_limited_alteration_description", "dob_limited_alteration_description_units"),
    ("hpd_violation_blank", "wvxf-dwi5", "violationid",
     "hpd_violation_description", "hpd_violation_description_units"),
    ("nycha_violation_blank", "im9z-53hg", "viol_seq_no",
     "nycha_violation_description", "nycha_violation_description_units"),
    ("elevator_application", "kfp4-dz4h", "job_filing_number",
     "dob_elevator_permit_description", "dob_elevator_permit_description_units"),
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
    stem = f"additional-official-description-{source}"
    database = work / f"{stem}.db"
    run(python, root / "tools/merges/mine_additional_official_description_units.py",
        "--source", source, "--db", database)
    run(python, root / "tools/local_model/export_dob_description_packets.py",
        "--descriptions-db", database, "--catalog-db", catalog,
        "--output", work / f"{stem}-packets.jsonl",
        "--progress-source", f"additional_official_description_{source}",
        "--dataset", dataset, "--id-field", id_field, "--packet-prefix", stem,
        "--source-type", source_type, "--dedupe-building-labels")
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
        "--methodology", "Explicit apartment label in an official direct-BBL NYC agency description; deterministically parsed, deduplicated by building and label, reviewed by local Qwen, and retained with verbatim evidence",
        "--match-rationale", "The agency record supplies a direct BBL and verbatim unit-label evidence",
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
    path = work / "additional-official-description-merge-summary.json"
    path.write_text(json.dumps(aggregate, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(aggregate, indent=2))


if __name__ == "__main__":
    main()
