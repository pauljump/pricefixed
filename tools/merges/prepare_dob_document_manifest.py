#!/usr/bin/env python3
"""Turn a browser-saved BIS certificate index into a reviewed-document manifest.

BIS profile and certificate pages are sometimes accessible in a normal browser
but rejected by unattended HTTP clients. A contributor can save the public
``C/O PDF Listing for Property`` page, then run this parser locally. It extracts
the exact public PDF form references and compares the page's block/lot and
premise with the queued target. It never treats a shared-BBL document as exact
address evidence.
"""
import argparse
import csv
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urljoin

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pricefixed.engine.crosswalk import normalize_address
from pricefixed.engine.identifiers import normalize_bbl


BoroughCode = {"MANHATTAN": "1", "BRONX": "2", "BROOKLYN": "3", "QUEENS": "4", "STATEN ISLAND": "5"}
FIELDS = (
    "property", "target_address", "target_normalized_address", "target_bbl",
    "bis_premise", "bis_bbl", "bis_bin", "document_type", "source_ref",
    "source_url", "document_url", "document_filename", "local_pdf",
    "identity_scope", "review_status", "unit_label", "exact_address_match",
    "observed_at", "notes",
)


class _BISFormParser(HTMLParser):
    """Capture only form metadata and visible text from a saved BIS page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.forms = []
        self._form = None
        self.text_parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag.lower() == "form":
            self._form = {"action": attrs.get("action", ""), "method": attrs.get("method", "get"), "inputs": {}}
        elif tag.lower() == "input" and self._form is not None:
            name = attrs.get("name")
            if name:
                self._form["inputs"][name] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag.lower() == "form" and self._form is not None:
            self.forms.append(self._form)
            self._form = None

    def handle_data(self, data):
        self.text_parts.append(data)


def _page_metadata(html):
    parser = _BISFormParser()
    parser.feed(html)
    text = re.sub(r"\s+", " ", " ".join(parser.text_parts)).strip()
    borough = ""
    for name in sorted(BoroughCode, key=len, reverse=True):
        if re.search(rf"\b{re.escape(name)}\b", text, re.I):
            borough = name
            break
    premise_match = re.search(
        r"Premises:\s*(.*?)\s+(?:MANHATTAN|BRONX|BROOKLYN|QUEENS|STATEN ISLAND)\s+BIN:",
        text, re.I,
    )
    bin_match = re.search(r"\bBIN:\s*(\d+)", text, re.I)
    block_match = re.search(r"\bBlock:\s*(\d+)", text, re.I)
    lot_match = re.search(r"\bLot:\s*(\d+)", text, re.I)
    block = block_match.group(1) if block_match else ""
    lot = lot_match.group(1) if lot_match else ""
    bis_bbl = ""
    if borough and block and lot:
        bis_bbl = normalize_bbl(f"{BoroughCode[borough]}{int(block):05d}{int(lot):04d}") or ""
    return {
        "premise": premise_match.group(1).strip() if premise_match else "",
        "bin": bin_match.group(1) if bin_match else "",
        "bis_bbl": bis_bbl,
        "forms": parser.forms,
    }


def _document_rows(html, index_url):
    metadata = _page_metadata(html)
    rows = []
    for form in metadata["forms"]:
        inputs = form["inputs"]
        filename = inputs.get("passcofonumber", "").strip()
        if not filename:
            continue
        keys = ("cofomatadata1", "cofomatadata2", "cofomatadata3", "cofomatadata4", "cofomatadata5")
        if not all(inputs.get(key, "").strip() for key in keys):
            continue
        params = [("passjobnumber", "null")]
        params.extend((key, inputs[key]) for key in keys)
        document_base = urljoin(index_url, "CofoDocumentContentServlet")
        rows.append({
            "premise": metadata["premise"],
            "bin": metadata["bin"],
            "bis_bbl": metadata["bis_bbl"],
            "document_type": inputs.get("cofomatadata1", "COFO"),
            "source_ref": f"bis-co:{metadata['bin']}:{filename}",
            "source_url": index_url,
            "document_url": f"{document_base}?{urlencode(params)}",
            "document_filename": filename,
        })
    return metadata, rows


def _target_rows(targets, metadata):
    target_rows = []
    premise_normalized = normalize_address(metadata["premise"])
    for target in targets:
        target_address = target.get("address") or target.get("target_address") or ""
        target_normalized = normalize_address(target.get("normalized_address") or target_address)
        target_bbl = normalize_bbl(target.get("resolved_bbl") or target.get("bbl")) or ""
        same_bbl = bool(target_bbl and target_bbl == metadata["bis_bbl"])
        same_address = bool(target_normalized and target_normalized == premise_normalized)
        if not same_bbl and not same_address:
            continue
        if not same_bbl:
            scope = "bbl_mismatch"
            note = "BIS page premise matches the target address, but BIS block/lot disagrees with the queued BBL."
        elif same_address:
            scope = "exact_premise"
            note = "BIS page premise and queued target address match; the PDF still requires document-level review."
        else:
            scope = "shared_bbl"
            note = "BIS page is on the same BBL but names a different premise; do not use its unit labels as exact-address evidence."
        target_rows.append({
            "property": target.get("property", ""),
            "target_address": target_address,
            "target_normalized_address": target_normalized,
            "target_bbl": target_bbl,
            "identity_scope": scope,
            "notes": note,
        })
    return target_rows


def build_manifest(html, index_url, targets=(), pdf_dir=""):
    """Return document rows joined to queued targets without creating units."""
    metadata, documents = _document_rows(html, index_url)
    matches = _target_rows(targets, metadata)
    output = []
    for document in documents:
        joined = matches or [{
            "property": "", "target_address": "", "target_normalized_address": "",
            "target_bbl": "", "identity_scope": "no_queue_match",
            "notes": "No queued target matched the BIS page's premise or BBL.",
        }]
        for target in joined:
            local_pdf = ""
            if pdf_dir:
                local_pdf = str(Path(pdf_dir) / document["document_filename"])
            output.append({
                **target,
                "bis_premise": document["premise"],
                "bis_bbl": document["bis_bbl"],
                "bis_bin": document["bin"],
                "document_type": document["document_type"],
                "source_ref": document["source_ref"],
                "source_url": document["source_url"],
                "document_url": document["document_url"],
                "document_filename": document["document_filename"],
                "local_pdf": local_pdf,
                "review_status": "needs_pdf_review",
                "unit_label": "",
                "exact_address_match": "" if target["identity_scope"] != "exact_premise" else "pending_pdf_review",
                "observed_at": "",
            })
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index-html", required=True, help="BIS C/O PDF Listing HTML saved from the browser")
    parser.add_argument("--index-url", required=True, help="Exact BIS C/O listing URL shown in the browser")
    parser.add_argument("--targets", required=True, help="Existing exact-address target queue CSV")
    parser.add_argument("--out", required=True)
    parser.add_argument("--pdf-dir", default="", help="Optional directory where contributors will save matching PDFs")
    args = parser.parse_args()
    with Path(args.index_html).open(encoding="utf-8") as handle:
        html = handle.read()
    with Path(args.targets).open(encoding="utf-8", newline="") as handle:
        targets = list(csv.DictReader(handle))
    rows = build_manifest(html, args.index_url, targets, args.pdf_dir)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} BIS document manifest rows to {output}")


if __name__ == "__main__":
    main()
