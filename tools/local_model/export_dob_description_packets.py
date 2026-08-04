#!/usr/bin/env python3
"""Export net-new DOB description candidates as local-Qwen JSONL packets."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.engine.dedupe import normalize_unit
from pricefixed.engine.unit_mentions import extract_explicit_unit_labels


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptions-db", required=True)
    parser.add_argument("--catalog-db", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--progress-source", default="dob_descriptions")
    parser.add_argument("--dataset", default="w9ak-ipjd")
    parser.add_argument("--id-field", default="job_filing_number")
    parser.add_argument("--packet-prefix", default="dob-description")
    parser.add_argument("--source-type", default="dob_job_description")
    parser.add_argument(
        "--parser-delta-only", action="store_true",
        help="export only labels newly recognized by the current deterministic parser",
    )
    args = parser.parse_args()
    source = sqlite3.connect(f"file:{Path(args.descriptions_db).resolve()}?mode=ro", uri=True)
    state = source.execute(
        "SELECT complete FROM progress WHERE source=?", (args.progress_source,)
    ).fetchone()
    if not state or state[0] != 1:
        raise SystemExit("DOB description mining is incomplete")
    catalog = sqlite3.connect(f"file:{Path(args.catalog_db).resolve()}?mode=ro", uri=True)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with output.open("w", encoding="utf-8") as handle:
        rows = source.execute(
            "SELECT job_filing_number,bbl,address,description,extracted_labels,filing_date "
            "FROM descriptions WHERE status='explicit_candidate' ORDER BY job_filing_number"
        )
        for job, bbl, address, description, labels_json, filing_date in rows:
            if not bbl:
                continue
            stored_labels = json.loads(labels_json)
            if args.parser_delta_only:
                stored = {normalize_unit(label) for label in stored_labels}
                labels = [
                    label for label in extract_explicit_unit_labels(description)
                    if normalize_unit(label) not in stored
                ]
            else:
                labels = stored_labels
            missing = []
            for label in labels:
                normalized = normalize_unit(label)
                if normalized and not catalog.execute(
                    "SELECT 1 FROM units WHERE bbl=? AND normalized_unit=?", (bbl, normalized)
                ).fetchone():
                    missing.append(label)
            if not missing:
                continue
            url = f"https://data.cityofnewyork.us/resource/{args.dataset}.json?" + urlencode({
                args.id_field: job
            })
            packet = {
                "id": f"{args.packet_prefix}-{job}",
                "source_ref": job,
                "source_type": args.source_type,
                "target_address": address,
                "source_url": url,
                "text": description,
                "candidate_labels": missing,
                "bbl": bbl,
                "observed_at": filing_date,
            }
            handle.write(json.dumps(packet, ensure_ascii=True) + "\n")
            written += 1
    source.close()
    catalog.close()
    print(f"wrote {written} net-new DOB description packets to {output}")


if __name__ == "__main__":
    main()
