#!/usr/bin/env python3
"""Capture public HPD historical image cards with their provenance intact.

HPD Online exposes historical image-card metadata and the corresponding PDF
through its public API. This script captures one building's cards, preserving
the API metadata, document identifiers, retrieval time, and PDF checksums. It
is a source-capture tool only: it never extracts or imports apartment units.
"""

import argparse
import base64
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


TOKEN_URL = "https://mspwvw-hpdleov3.nyc.gov/authenticationservice/1.0/api/Apim/token"
API_BASE = "https://mspwvw-hpdleov3.nyc.gov/hpdonline.api/1.0/api"
DOCUMENT_BASE = "https://mspwvw-hpdleov3.nyc.gov/DocService/v1/api"
USER_AGENT = "pricefixed-public-records/1.0"


def _json_request(url, *, method="GET", body=None, headers=None):
    request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    request_headers.update(headers or {})
    request = Request(url, data=body, headers=request_headers, method=method)
    with urlopen(request, timeout=180) as response:
        return json.loads(response.read())


def _api_token():
    response = _json_request(
        TOKEN_URL,
        method="POST",
        body=b"{}",
        headers={"Content-Type": "application/json"},
    )
    token = str(response.get("token") or "").strip()
    if not token:
        raise RuntimeError("HPD public token response did not contain a token")
    return token


def _authenticated_json(url, token):
    return _json_request(url, headers={"ApiKey": f"Bearer {token}"})


def _safe_file_type(value):
    value = str(value or "pdf").strip().lower()
    return value if value.isalnum() else "pdf"


def capture(building_id, out_dir, doc_ids=None, token=None):
    """Capture selected or all public historical cards for one HPD building."""
    building_id = int(building_id)
    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    token = token or _api_token()

    list_url = f"{API_BASE}/building/historicimage/list/{building_id}"
    list_payload = _authenticated_json(list_url, token)
    cards = list_payload.get("responseData") or []
    selected = {str(value) for value in (doc_ids or [])}
    if selected:
        cards = [card for card in cards if str(card.get("docId")) in selected]

    raw_list_path = out_dir / f"historic-image-list-{building_id}.json"
    raw_list_path.write_text(json.dumps(list_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    captured = []
    for card in cards:
        required = ("imageSeqNo", "docId", "docTypeId", "subDocTypeId")
        if any(card.get(key) in (None, "") for key in required):
            raise RuntimeError(f"HPD card metadata is missing a document identifier: {card!r}")
        image_seq_no = card["imageSeqNo"]
        doc_id = card["docId"]
        doc_type_id = card["docTypeId"]
        sub_doc_type_id = card["subDocTypeId"]
        document_url = (
            f"{DOCUMENT_BASE}/documents/content/"
            f"{image_seq_no}/{doc_id}/{doc_type_id}/{sub_doc_type_id}"
        )
        document_payload = _authenticated_json(document_url, token)
        encoded = (document_payload.get("responseData") or {}).get("documentBytes")
        if not encoded:
            raise RuntimeError(f"HPD document response did not contain bytes: {document_url}")
        document_bytes = base64.b64decode(encoded, validate=True)
        if not document_bytes.startswith(b"%PDF"):
            raise RuntimeError(f"HPD document response was not a PDF: {document_url}")

        filename = f"Icard_{image_seq_no}.{_safe_file_type(card.get('fileType'))}"
        pdf_path = out_dir / filename
        pdf_path.write_bytes(document_bytes)
        captured.append({
            "building_id": building_id,
            "image_seq_no": image_seq_no,
            "doc_id": doc_id,
            "doc_type_id": doc_type_id,
            "sub_doc_type_id": sub_doc_type_id,
            "doc_name": card.get("docName", ""),
            "doc_description": card.get("docDescription", ""),
            "date_taken": card.get("dateTaken", ""),
            "file_type": card.get("fileType", ""),
            "source_ref": f"hpd-icard:{building_id}:{image_seq_no}",
            "metadata_url": list_url,
            "document_url": document_url,
            "local_file": str(pdf_path),
            "retrieved_at": retrieved_at,
            "sha256": hashlib.sha256(document_bytes).hexdigest(),
        })

    manifest = {
        "building_id": building_id,
        "metadata_url": list_url,
        "retrieved_at": retrieved_at,
        "raw_list_file": str(raw_list_path),
        "cards": captured,
    }
    manifest_path = out_dir / f"historic-image-manifest-{building_id}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--building-id", required=True, type=int, action="append",
        help="HPD Online building ID; repeat to capture multiple buildings",
    )
    parser.add_argument("--out-dir", required=True, help="Directory for PDFs and provenance JSON")
    parser.add_argument(
        "--doc-id", action="append", default=[],
        help="Capture only this HPD document ID; repeat for multiple cards (default: all)",
    )
    args = parser.parse_args()
    if any(building_id <= 0 for building_id in args.building_id):
        parser.error("--building-id must be positive")
    total = 0
    token = _api_token() if len(args.building_id) > 1 else None
    for building_id in args.building_id:
        destination = Path(args.out_dir)
        if len(args.building_id) > 1:
            destination /= str(building_id)
        manifest = capture(building_id, destination, args.doc_id, token=token)
        total += len(manifest["cards"])
        print(f"building_id={building_id} captured={len(manifest['cards'])}")
    print(f"captured {total} HPD historical image cards")


if __name__ == "__main__":
    sys.exit(main())
