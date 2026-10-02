#!/usr/bin/env python3
"""Run the electrical-detail queue after all earlier local-model passes."""
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
    stem = "dob-electrical-detail"
    database = work / f"{stem}-units.db"
    run(python, root / "tools/merges/mine_dob_electrical_detail_units.py", "--db", database)
    run(python, root / "tools/local_model/export_dob_description_packets.py",
        "--descriptions-db", database, "--catalog-db", catalog,
        "--output", work / f"{stem}-packets.jsonl",
        "--progress-source", "dob_electrical_details_v3", "--dataset", "xmmq-y7za",
        "--id-field", "unique_id", "--packet-prefix", stem,
        "--source-type", "dob_electrical_permit_detail",
        "--source-parser", "electrical_detail")
    run(python, root / "tools/local_model/run_qwen_extraction.py",
        "--input", work / f"{stem}-packets.jsonl",
        "--output", work / f"{stem}-results.jsonl", "--batch-size", "8")
    run(python, root / "tools/local_model/prepare_dob_description_results.py",
        "--packets", work / f"{stem}-packets.jsonl",
        "--results", work / f"{stem}-results.jsonl",
        "--accepted", work / f"{stem}-accepted.csv",
        "--rejected", work / f"{stem}-rejected.csv",
        "--summary", work / f"{stem}-summary.json",
        "--source-parser", "electrical_detail")
    run(python, root / "tools/merges/merge_dob_description_results.py",
        "--csv", work / f"{stem}-accepted.csv", "--catalog-db", catalog,
        "--summary", work / f"{stem}-merge-summary.json",
        "--source", "dob_electrical_permit_detail_units",
        "--methodology", "Explicit apartment label in an official DOB NOW electrical permit detail row; deterministically parsed, reviewed by local Qwen, and retained with verbatim evidence",
        "--match-rationale", "DOB electrical permit detail supplies the apartment label and joins by filing number to the parent DOB BBL and address",
        "--apply")


if __name__ == "__main__":
    main()
