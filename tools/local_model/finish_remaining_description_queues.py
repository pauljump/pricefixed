#!/usr/bin/env python3
"""Run remaining official DOB and HPD description queues in sequence."""
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


def process(root, python, work, catalog, stem, database, progress_source, dataset, id_field,
            source_type, catalog_source, methodology, rationale):
    run(python, root / "tools/local_model/export_dob_description_packets.py",
        "--descriptions-db", database, "--catalog-db", catalog,
        "--output", work / f"{stem}-packets.jsonl", "--progress-source", progress_source,
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
    run(python, root / "tools/merges/merge_dob_description_results.py",
        "--csv", work / f"{stem}-accepted.csv", "--catalog-db", catalog,
        "--summary", work / f"{stem}-merge-summary.json", "--source", catalog_source,
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

    dob_db = work / "dob-violation-description-units.db"
    run(python, root / "tools/merges/mine_dob_violation_description_units.py", "--db", dob_db)
    process(root, python, work, catalog, "dob-violation-description", dob_db,
            "dob_violation_descriptions", "3h2n-5cm9", "isn_dob_bis_viol",
            "dob_violation_description", "dob_violation_description_units",
            "Explicit apartment label in an official legacy DOB violation description or disposition; deterministically parsed, reviewed by local Qwen, and retained with verbatim evidence",
            "DOB violation supplies the BBL and verbatim apartment-label evidence")

    for source, stem, dataset, id_field, catalog_source, label in (
        ("hwo", "hpd-hwo-description", "sbnd-xujn", "hwoid", "hpd_hwo_description_units", "HPD handyman work order"),
        ("omo_blank", "hpd-omo-description", "mdbu-nrqn", "omoid", "hpd_omo_description_units", "HPD open-market work order"),
    ):
        database = work / f"{stem}-units.db"
        run(python, root / "tools/merges/mine_hpd_work_description_units.py",
            "--source", source, "--db", database)
        process(root, python, work, catalog, stem, database,
                f"hpd_{source}_descriptions", dataset, id_field,
                f"{source}_work_description", catalog_source,
                f"Explicit apartment label in an official {label} description; deterministically parsed, reviewed by local Qwen, and retained with verbatim evidence",
                f"{label} supplies the BBL and verbatim apartment-label evidence")


if __name__ == "__main__":
    main()
