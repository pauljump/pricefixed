#!/usr/bin/env python3
"""Use local Qwen to recover addresses from DOF statements missed by regex."""
import argparse
import csv
import json
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

from run_qwen_extraction import call_model, DEFAULT_BASE_URL, DEFAULT_MODEL


def statement_text(url):
    request = Request(url, headers={"User-Agent": "pricefixed-public-records/1.0"})
    with urlopen(request, timeout=60) as response:
        pdf = response.read()
    result = subprocess.run(
        ["pdftotext", "-", "-"], input=pdf, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, check=True,
    )
    return result.stdout.decode("utf-8", errors="replace").strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()
    done = set()
    output = Path(args.output)
    if output.exists():
        with output.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    done.add(json.loads(line)["id"])
    rows = []
    with open(args.input, encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["status"] == "no_address_in_statement"]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8") as handle:
        for row in rows:
            record_id = f"dof-{row['unit_lot_bbl']}"
            if record_id in done:
                continue
            result = {"id": record_id, "unit_lot_bbl": row["unit_lot_bbl"],
                      "unit_designation": row["unit_designation"],
                      "source_url": row["source_url"], "model": args.model}
            try:
                text = statement_text(row["source_url"])
                if not text:
                    result["status"] = "no_text_layer"
                else:
                    raw, parsed = call_model(
                        args.base_url, args.model,
                        {"id": record_id, "source_type": "dof_statement",
                         "target_address": "", "source_url": row["source_url"], "text": text},
                        1024, 0.2, 180,
                    )
                    result.update({"status": "ok" if parsed else "invalid_json",
                                   "parsed": parsed, "raw": raw})
            except Exception as exc:
                result.update({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
            handle.write(json.dumps(result, ensure_ascii=True) + "\n")
            handle.flush()
            print(f"processed {record_id}", flush=True)


if __name__ == "__main__":
    main()
