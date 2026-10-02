#!/usr/bin/env python3
"""Convert a reviewed public SecureCafe browser capture into a listings DB.

Some SecureCafe properties are public in an interactive browser but return a
Cloudflare challenge to a plain HTTP client. This importer accepts the small,
reviewable JSON produced by that capture workflow. It only accepts rows that
contain an explicit apartment label, preserves the source URLs and the original
row payload, and never expands a floorplan or availability count into units.
"""

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from pricefixed.core import init_db, upsert_listings


SOURCE = "securecafe"


def _number(value):
    match = re.search(r"[\d,]+(?:\.\d+)?", str(value or ""))
    if not match:
        return None
    return float(match.group(0).replace(",", ""))


def _bed_bath(caption):
    text = str(caption or "")
    beds = 0 if re.search(r"studio|0\s*bed", text, re.I) else None
    bed_match = re.search(r"(\d+)\s*bed", text, re.I)
    if bed_match:
        beds = int(bed_match.group(1))
    bath_match = re.search(r"(\d+(?:\.\d+)?)\s*bath", text, re.I)
    baths = float(bath_match.group(1)) if bath_match else None
    return beds, baths


def _subdomain(availability_url):
    host = urlparse(availability_url).hostname or ""
    suffix = ".securecafe.com"
    if not host.endswith(suffix) or not host[: -len(suffix)]:
        return ""
    return host[: -len(suffix)]


def _address_parts(address):
    """Return the street premise, borough, and ZIP from a display address."""
    value = str(address or "").strip()
    zipcode_match = re.search(r"\b(\d{5})\b", value)
    zipcode = zipcode_match.group(1) if zipcode_match else None
    street = value.split(",", 1)[0].strip()
    borough = "Manhattan" if re.search(r"New York\s*,?\s*NY", value, re.I) else None
    return street, borough, zipcode


def build_listings(capture):
    """Return normal listing rows and rejected rows from a capture payload."""
    retrieved_at = str(capture.get("retrieved_at") or "").strip()
    listings = []
    rejected = []
    for source in capture.get("sources") or []:
        property_name = str(source.get("property") or "").strip()
        address = str(source.get("address") or "").strip()
        official_url = str(source.get("official_url") or "").strip()
        availability_url = str(source.get("availability_url") or "").strip()
        subdomain = _subdomain(availability_url)
        if not property_name or not address or not official_url or not availability_url or not subdomain:
            rejected.append({"property": property_name, "address": address,
                             "rejection_reason": "missing_or_invalid_source_metadata"})
            continue
        street_address, borough, zipcode = _address_parts(address)
        for raw_row in source.get("rows") or []:
            row = dict(raw_row)
            unit = str(row.get("unit") or "").strip().lstrip("#")
            if not unit:
                row.update({"property": property_name, "address": address,
                            "rejection_reason": "missing_explicit_unit_label"})
                rejected.append(row)
                continue
            beds, baths = _bed_bath(row.get("caption"))
            source_id = f"sc-{subdomain}-{unit}"
            listings.append({
                "source_id": source_id,
                "building_name": property_name,
                "address": street_address,
                "unit_number": unit,
                "bedrooms": beds,
                "bathrooms": baths,
                "price": _number(row.get("rent")),
                "sqft": _number(row.get("sqft")),
                "available_date": str(row.get("available") or "").strip() or None,
                "lease_terms": None,
                "amenities": None,
                "description": None,
                "floor_plan_url": None,
                "image_urls": None,
                "latitude": None,
                "longitude": None,
                "neighborhood": None,
                "borough": borough,
                "zipcode": zipcode,
                "is_flex": 0,
                "is_rent_stabilized": 0,
                "finish_level": None,
                "raw_json": json.dumps({
                    "capture_retrieved_at": retrieved_at,
                    "property": property_name,
                    "source_address": address,
                    "resolved_street_address": street_address,
                    "bbl": source.get("bbl"),
                    "bbl_evidence": source.get("bbl_evidence"),
                    "official_url": official_url,
                    "availability_url": availability_url,
                    "extraction_method": "browser_visible_dom_table",
                    "row": row,
                }, sort_keys=True),
            })
    return listings, rejected


def import_capture(capture_path, output_db):
    capture = json.loads(Path(capture_path).read_text(encoding="utf-8"))
    listings, rejected = build_listings(capture)
    conn = init_db(output_db)
    try:
        new_count, updated_count = upsert_listings(conn, listings, SOURCE)
    finally:
        conn.close()
    return {"listings": len(listings), "rejected": rejected,
            "new": new_count, "updated": updated_count}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", required=True, help="browser-capture JSON file")
    parser.add_argument("--output-db", required=True, help="listings SQLite output")
    parser.add_argument("--rejected", help="optional rejected-row JSON output")
    args = parser.parse_args()
    result = import_capture(args.capture, args.output_db)
    if args.rejected:
        Path(args.rejected).write_text(json.dumps(result["rejected"], indent=2), encoding="utf-8")
    print(f"imported capture rows: {result['listings']}")
    print(f"new listings: {result['new']}")
    print(f"updated listings: {result['updated']}")
    print(f"rejected rows: {len(result['rejected'])}")


if __name__ == "__main__":
    main()
