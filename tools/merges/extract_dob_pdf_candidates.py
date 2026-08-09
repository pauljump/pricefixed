#!/usr/bin/env python3
"""Extract review candidates from locally captured DOB PDFs.

This tool is deliberately not an importer. It uses ``pdftotext -layout`` when
available, preserves a short evidence excerpt, and marks every result for
review. Shared-BBL and BBL-mismatch documents can remain useful evidence, but
they are never promoted to exact-address candidates automatically.
"""
import argparse
import csv
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.engine.crosswalk import normalize_address
from pricefixed.engine.unit_mentions import extract_explicit_unit_labels


FIELDS = (
    "property", "target_address", "target_bbl", "bis_premise", "bis_bbl", "source_ref",
    "source_url", "document_url", "local_pdf", "observed_at", "unit_label",
    "identity_scope", "text_address_match", "status", "evidence",
)


def _search_text(text):
    """Create a conservative address-search form without treating all PDF text as an address."""
    value = str(text or "").upper().replace("\n", " ")
    value = re.sub(r"[,.]", " ", value)
    for long, short in (
        (" STREET", " ST"), (" AVENUE", " AVE"), (" ROAD", " RD"),
        (" DRIVE", " DR"), (" PLACE", " PL"), (" BOULEVARD", " BLVD"),
    ):
        value = value.replace(long, short)
    value = re.sub(r"\b(EAST|WEST|NORTH|SOUTH)\b", lambda m: m.group(1)[0], value)
    return re.sub(r"\s+", " ", value).strip()


def _evidence_excerpt(text):
    match = re.search(r"\b(?:APT|APTS|APARTMENT|APARTMENTS|UNIT|DWELLING UNITS?)\b", text, re.I)
    if not match:
        return re.sub(r"\s+", " ", text).strip()[:500]
    start = max(0, match.start() - 160)
    end = min(len(text), match.end() + 340)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def parse_pdf_text(manifest_row, text):
    """Return candidate rows from extracted text; no row is import-ready by default."""
    target_address = manifest_row.get("target_address", "")
    target_norm = normalize_address(target_address)
    text_match = bool(target_norm and target_norm in _search_text(text))
    labels = extract_explicit_unit_labels(text)
    scope = manifest_row.get("identity_scope", "")
    if scope == "bbl_mismatch":
        status = "bbl_mismatch"
    elif scope == "shared_bbl":
        status = "shared_bbl_candidate" if labels else "shared_bbl_no_explicit_unit_label"
    elif scope == "exact_premise" and not text_match:
        status = "address_not_in_pdf_text" if labels else "address_not_in_pdf_text_no_label"
    elif labels:
        status = "review_candidate"
    else:
        status = "no_explicit_unit_label"
    base = {
        "property": manifest_row.get("property", ""),
        "target_address": target_address,
        "target_bbl": manifest_row.get("target_bbl", ""),
        "bis_premise": manifest_row.get("bis_premise", ""),
        "bis_bbl": manifest_row.get("bis_bbl", ""),
        "source_ref": manifest_row.get("source_ref", ""),
        "source_url": manifest_row.get("document_url") or manifest_row.get("source_url", ""),
        "document_url": manifest_row.get("document_url", ""),
        "local_pdf": manifest_row.get("local_pdf", ""),
        "observed_at": manifest_row.get("observed_at", ""),
        "identity_scope": scope,
        "text_address_match": "yes" if text_match else "no",
        "status": status,
        "evidence": _evidence_excerpt(text),
    }
    return [{**base, "unit_label": label} for label in labels] or [{**base, "unit_label": ""}]


def extract_text(pdf_path, pdftotext="pdftotext"):
    result = subprocess.run(
        [pdftotext, "-layout", str(pdf_path), "-"],
        check=False, capture_output=True, text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"pdftotext exited {result.returncode}")
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--pdftotext", default="pdftotext")
    args = parser.parse_args()
    rows = []
    with Path(args.manifest).open(encoding="utf-8", newline="") as handle:
        for manifest_row in csv.DictReader(handle):
            pdf_path = manifest_row.get("local_pdf", "")
            if not pdf_path or not Path(pdf_path).exists():
                rows.append({**{field: manifest_row.get(field, "") for field in FIELDS},
                             "unit_label": "", "status": "missing_pdf", "evidence": ""})
                continue
            try:
                text = extract_text(pdf_path, args.pdftotext)
                rows.extend(parse_pdf_text(manifest_row, text))
            except Exception as exc:  # noqa: BLE001 — preserve one failed document for review
                rows.append({**{field: manifest_row.get(field, "") for field in FIELDS},
                             "unit_label": "", "status": f"pdf_extract_error:{type(exc).__name__}",
                             "evidence": str(exc)})
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} DOB PDF review candidates to {output}")


if __name__ == "__main__":
    main()
