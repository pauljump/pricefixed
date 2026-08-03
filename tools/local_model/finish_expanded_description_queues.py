#!/usr/bin/env python3
"""Run expanded DOB and OATH description queues after the base DOB pipeline."""
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


def process_queue(root, python, work, catalog, stem, source, methodology, rationale):
    packets = work / f"{stem}-packets.jsonl"
    results = work / f"{stem}-results.jsonl"
    accepted = work / f"{stem}-accepted.csv"
    rejected = work / f"{stem}-rejected.csv"
    summary = work / f"{stem}-summary.json"
    run(python, root / "tools/local_model/run_qwen_extraction.py",
        "--input", packets, "--output", results, "--batch-size", "8")
    run(python, root / "tools/local_model/prepare_dob_description_results.py",
        "--packets", packets, "--results", results, "--accepted", accepted,
        "--rejected", rejected, "--summary", summary)
    run(python, root / "tools/merges/merge_dob_description_results.py",
        "--csv", accepted, "--catalog-db", catalog,
        "--summary", work / f"{stem}-merge-summary.json", "--source", source,
        "--methodology", methodology, "--match-rationale", rationale, "--apply")


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

    run(python, root / "tools/merges/mine_dob_description_units.py",
        "--db", work / "dob-description-units.db", "--reclassify")
    run(python, root / "tools/local_model/export_dob_description_packets.py",
        "--descriptions-db", work / "dob-description-units.db", "--catalog-db", catalog,
        "--output", work / "dob-description-expanded-packets.jsonl",
        "--progress-source", "dob_descriptions", "--dataset", "w9ak-ipjd",
        "--id-field", "job_filing_number", "--packet-prefix", "dob-description-expanded",
        "--source-type", "dob_job_description_expanded")
    process_queue(
        root, python, work, catalog, "dob-description-expanded",
        "dob_now_job_description_units",
        "Explicit apartment label in an official DOB NOW job description; deterministically parsed, reviewed by local Qwen, and retained with verbatim evidence",
        "DOB NOW supplies the BBL and verbatim apartment-label evidence",
    )

    run(python, root / "tools/merges/mine_oath_description_units.py",
        "--db", work / "oath-dob-description-units.db")
    run(python, root / "tools/local_model/export_dob_description_packets.py",
        "--descriptions-db", work / "oath-dob-description-units.db", "--catalog-db", catalog,
        "--output", work / "oath-dob-description-packets.jsonl",
        "--progress-source", "oath_dob_descriptions", "--dataset", "jz4z-kudi",
        "--id-field", "ticket_number", "--packet-prefix", "oath-dob-description",
        "--source-type", "oath_dob_violation_description")
    process_queue(
        root, python, work, catalog, "oath-dob-description",
        "oath_dob_violation_description_units",
        "Explicit apartment label in an official DOB-issued OATH case; deterministically parsed, reviewed by local Qwen, and retained with verbatim evidence",
        "The OATH case supplies official block/lot location and verbatim apartment-label evidence",
    )


if __name__ == "__main__":
    main()
