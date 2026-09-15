#!/usr/bin/env python3
"""Convert downloaded PDFs into page-level JSONL packets for local extraction.

The manifest is CSV with: id,local_path,source_type,target_address,source_url.
Text extraction is deterministic and uses local ``pdfinfo`` and ``pdftotext``.
Scanned PDFs are reported and skipped for a later OCR pass.
"""
import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path


def page_count(path):
    result = subprocess.run(["pdfinfo", str(path)], check=True, capture_output=True, text=True)
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise RuntimeError(f"pdfinfo did not report pages: {path}")


def page_text(path, page):
    result = subprocess.run(
        ["pdftotext", "-f", str(page), "-l", str(page), "-layout", str(path), "-"],
        check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--skipped", required=True, help="JSONL report for missing or scanned PDFs")
    args = parser.parse_args()
    output = Path(args.output)
    skipped = Path(args.skipped)
    output.parent.mkdir(parents=True, exist_ok=True)
    skipped.parent.mkdir(parents=True, exist_ok=True)
    packets = skipped_count = 0
    with open(args.manifest, encoding="utf-8", newline="") as source, \
            output.open("w", encoding="utf-8") as packet_file, \
            skipped.open("w", encoding="utf-8") as skipped_file:
        for row in csv.DictReader(source):
            path = Path(row["local_path"])
            base = {key: row.get(key, "") for key in
                    ("id", "source_type", "target_address", "source_url")}
            if not path.is_file():
                skipped_file.write(json.dumps({**base, "status": "missing_file"}) + "\n")
                skipped_count += 1
                continue
            try:
                pages = page_count(path)
                document_packets = []
                for page in range(1, pages + 1):
                    text = page_text(path, page)
                    if text:
                        document_packets.append({**base, "id": f"{row['id']}-page-{page}",
                                                 "page": page, "text": text})
                for packet in document_packets:
                    packet_file.write(json.dumps(packet, ensure_ascii=True) + "\n")
                packets += len(document_packets)
                if not document_packets:
                    skipped_file.write(json.dumps({**base, "status": "no_text_layer"}) + "\n")
                    skipped_count += 1
            except (OSError, subprocess.CalledProcessError, ValueError, RuntimeError) as exc:
                skipped_file.write(json.dumps({**base, "status": "error", "error": str(exc)}) + "\n")
                skipped_count += 1
    print(f"wrote {packets} text packets to {output}")
    print(f"wrote {skipped_count} skipped documents to {skipped}")


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as exc:
        sys.exit(f"required local command or file missing: {exc}")
