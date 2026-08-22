#!/usr/bin/env python3
"""Finish, verify, and merge current and legacy DOB local-model queues."""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


def run(*parts):
    print("running:", " ".join(str(part) for part in parts), flush=True)
    subprocess.run([str(part) for part in parts], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-runner-pid", type=int, required=True)
    parser.add_argument("--catalog-db", required=True)
    parser.add_argument("--work-dir", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    work = Path(args.work_dir)
    python = sys.executable

    while True:
        try:
            os.kill(args.current_runner_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(60)

    run(
        python, root / "tools/local_model/prepare_dob_description_results.py",
        "--packets", work / "dob-description-qwen-packets.jsonl",
        "--results", work / "dob-description-qwen-results.jsonl",
        "--accepted", work / "dob-description-qwen-accepted.csv",
        "--rejected", work / "dob-description-qwen-rejected.csv",
        "--summary", work / "dob-description-qwen-summary.json",
    )
    run(
        python, root / "tools/merges/merge_dob_description_results.py",
        "--csv", work / "dob-description-qwen-accepted.csv",
        "--catalog-db", args.catalog_db,
        "--summary", work / "dob-description-merge-summary.json",
        "--source", "dob_now_job_description_units", "--apply",
    )
    run(
        python, root / "tools/local_model/export_dob_description_packets.py",
        "--descriptions-db", work / "legacy-dob-description-units.db",
        "--catalog-db", args.catalog_db,
        "--output", work / "legacy-dob-description-qwen-packets.jsonl",
        "--progress-source", "legacy_dob_descriptions",
        "--dataset", "ic3t-wcy2", "--id-field", "job_s1_no",
        "--packet-prefix", "legacy-dob-description",
        "--source-type", "legacy_dob_job_description",
    )
    run(
        python, root / "tools/local_model/run_qwen_extraction.py",
        "--input", work / "legacy-dob-description-qwen-packets.jsonl",
        "--output", work / "legacy-dob-description-qwen-results.jsonl",
        "--batch-size", "8",
    )
    run(
        python, root / "tools/local_model/prepare_dob_description_results.py",
        "--packets", work / "legacy-dob-description-qwen-packets.jsonl",
        "--results", work / "legacy-dob-description-qwen-results.jsonl",
        "--accepted", work / "legacy-dob-description-qwen-accepted.csv",
        "--rejected", work / "legacy-dob-description-qwen-rejected.csv",
        "--summary", work / "legacy-dob-description-qwen-summary.json",
    )
    run(
        python, root / "tools/merges/merge_dob_description_results.py",
        "--csv", work / "legacy-dob-description-qwen-accepted.csv",
        "--catalog-db", args.catalog_db,
        "--summary", work / "legacy-dob-description-merge-summary.json",
        "--source", "legacy_dob_job_description_units", "--apply",
    )


if __name__ == "__main__":
    main()
