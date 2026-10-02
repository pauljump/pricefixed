#!/usr/bin/env python3
"""Run the historical DOB ECB description queue after the OATH pipeline."""
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

    stem = "ecb-dob-description"
    run(python, root / "tools/merges/mine_ecb_description_units.py",
        "--db", work / f"{stem}-units.db")
    run(python, root / "tools/local_model/export_dob_description_packets.py",
        "--descriptions-db", work / f"{stem}-units.db", "--catalog-db", catalog,
        "--output", work / f"{stem}-packets.jsonl",
        "--progress-source", "ecb_dob_descriptions", "--dataset", "6bgk-3dad",
        "--id-field", "ecb_violation_number", "--packet-prefix", stem,
        "--source-type", "dob_ecb_violation_description")
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
        "--source", "dob_ecb_violation_description_units",
        "--methodology", "Explicit apartment label in an official DOB ECB violation description; deterministically parsed, reviewed by local Qwen, and retained with verbatim evidence",
        "--match-rationale", "DOB ECB supplies the BBL and verbatim apartment-label evidence",
        "--apply")


if __name__ == "__main__":
    main()
