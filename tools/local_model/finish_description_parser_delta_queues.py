#!/usr/bin/env python3
"""Verify labels exposed by deterministic parser improvements after primary queues."""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


QUEUES = (
    ("dob-now", "dob-description-units.db", "dob_descriptions", "w9ak-ipjd",
     "job_filing_number", "dob_job_description_parser_delta", "dob_now_job_description_units"),
    ("legacy-dob", "legacy-dob-description-units.db", "legacy_dob_descriptions", "ic3t-wcy2",
     "job_s1_no", "legacy_dob_job_description_parser_delta", "legacy_dob_job_description_units"),
    ("oath-dob", "oath-dob-description-units.db", "oath_dob_descriptions", "jz4z-kudi",
     "ticket_number", "oath_dob_description_parser_delta", "oath_dob_violation_description_units"),
    ("ecb-dob", "ecb-dob-description-units.db", "ecb_dob_descriptions", "6bgk-3dad",
     "ecb_violation_number", "dob_ecb_description_parser_delta", "dob_ecb_violation_description_units"),
    ("dob-violation", "dob-violation-description-units.db", "dob_violation_descriptions", "3h2n-5cm9",
     "isn_dob_bis_viol", "dob_violation_parser_delta", "dob_violation_description_units"),
    ("hpd-hwo", "hpd-hwo-description-units.db", "hpd_hwo_descriptions", "sbnd-xujn",
     "hwoid", "hpd_hwo_parser_delta", "hpd_hwo_description_units"),
    ("hpd-omo", "hpd-omo-description-units.db", "hpd_omo_blank_descriptions", "mdbu-nrqn",
     "omoid", "hpd_omo_parser_delta", "hpd_omo_description_units"),
    ("dob-electrical", "dob-electrical-description-units.db", "dob_electrical_descriptions", "dm9a-ab7w",
     "job_filing_number", "dob_electrical_parser_delta", "dob_electrical_permit_description_units"),
    ("dob-approved-permit", "dob-approved-permit-description-units.db", "dob_approved_permit_descriptions", "rbx6-tga4",
     "work_permit", "dob_approved_permit_parser_delta", "dob_approved_permit_description_units"),
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
    stem, database_name, progress, dataset, id_field, source_type, catalog_source = config
    stem = f"description-parser-delta-{stem}"
    packets = work / f"{stem}-packets.jsonl"
    results = work / f"{stem}-results.jsonl"
    accepted = work / f"{stem}-accepted.csv"
    rejected = work / f"{stem}-rejected.csv"
    run(python, root / "tools/local_model/export_dob_description_packets.py",
        "--descriptions-db", work / database_name, "--catalog-db", catalog,
        "--output", packets, "--progress-source", progress,
        "--dataset", dataset, "--id-field", id_field, "--packet-prefix", stem,
        "--source-type", source_type, "--parser-delta-only")
    run(python, root / "tools/local_model/run_qwen_extraction.py",
        "--input", packets, "--output", results, "--batch-size", "8")
    run(python, root / "tools/local_model/prepare_dob_description_results.py",
        "--packets", packets, "--results", results,
        "--accepted", accepted, "--rejected", rejected,
        "--summary", work / f"{stem}-summary.json")
    merge_summary = work / f"{stem}-merge-summary.json"
    run(python, root / "tools/merges/merge_dob_description_results.py",
        "--csv", accepted, "--catalog-db", catalog, "--summary", merge_summary,
        "--source", catalog_source,
        "--methodology", "Explicit apartment label newly exposed by the current deterministic parser in an already-mined official description; reviewed by local Qwen and retained with verbatim evidence",
        "--match-rationale", "The original agency record supplies the BBL, address, and verbatim apartment-label evidence",
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
    python = sys.executable
    wait_for_pid(args.base_pipeline_pid)
    summaries = [
        process_queue(root, python, work, Path(args.catalog_db), config)
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
    path = work / "description-parser-delta-merge-summary.json"
    path.write_text(json.dumps(aggregate, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(aggregate, indent=2))


if __name__ == "__main__":
    main()
