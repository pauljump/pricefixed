#!/usr/bin/env python3
"""Run approved-permit description extraction after all earlier local-model passes."""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-pipeline-pid", type=int, required=True)
    parser.add_argument("--catalog-db", required=True)
    parser.add_argument("--work-dir", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    work = Path(args.work_dir)
    catalog = Path(args.catalog_db)
    python = sys.executable
    wait_for_pid(args.base_pipeline_pid)
    stem = "dob-approved-permit-description"
    database = work / f"{stem}-units.db"
    run(python, root / "tools/merges/mine_dob_approved_permit_description_units.py", "--db", database)
    run(python, root / "tools/local_model/export_dob_description_packets.py",
        "--descriptions-db", database, "--catalog-db", catalog,
        "--output", work / f"{stem}-packets.jsonl",
        "--progress-source", "dob_approved_permit_descriptions", "--dataset", "rbx6-tga4",
        "--id-field", "work_permit", "--packet-prefix", stem,
        "--source-type", "dob_approved_permit_description")
    run(python, root / "tools/local_model/run_qwen_extraction.py",
        "--input", work / f"{stem}-packets.jsonl",
        "--output", work / f"{stem}-results.jsonl", "--batch-size", "8")
    run(python, root / "tools/local_model/prepare_dob_description_results.py",
        "--packets", work / f"{stem}-packets.jsonl",
        "--results", work / f"{stem}-results.jsonl",
        "--accepted", work / f"{stem}-accepted.csv",
        "--rejected", work / f"{stem}-rejected.csv",
        "--summary", work / f"{stem}-summary.json")
    run(python, root / "tools/merges/merge_dob_description_results.py",
        "--csv", work / f"{stem}-accepted.csv", "--catalog-db", catalog,
        "--summary", work / f"{stem}-merge-summary.json",
        "--source", "dob_approved_permit_description_units",
        "--methodology", "Explicit apartment label in an official DOB NOW approved-permit description; deterministically parsed, reviewed by local Qwen, and retained with verbatim evidence",
        "--match-rationale", "DOB approved permit supplies the BBL and verbatim apartment-label evidence",
        "--apply")


if __name__ == "__main__":
    main()
