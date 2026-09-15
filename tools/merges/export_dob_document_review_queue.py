#!/usr/bin/env python3
"""Export exact-address DOB document targets with reproducible review links."""
import argparse
import csv
import re
from pathlib import Path
from urllib.parse import urlencode


DOB_NOW_PUBLIC_PORTAL = "https://a810-dobnow.nyc.gov/publish/app/user/newLogIn.html"
BIS_SEARCH = "https://a810-bisweb.nyc.gov/bisweb/bsqpm01.jsp"

FIELDS = (
    "property", "address", "normalized_address", "resolved_bbl", "listing_count",
    "direct_address_unit_count", "catalog_bbl_unit_count", "packet_exact_hit_count",
    "inventory_origin", "next_source", "bis_property_profile_url",
    "bis_bbl_building_map_url",
    "dob_now_public_portal_url", "review_status", "document_url", "evidence_type",
    "unit_label", "exact_address_match", "notes",
)


def split_address(address):
    """Return the BIS house number and street portion for a simple NYC address."""
    match = re.match(r"^\s*(\d+[A-Z]?(?:[-/]\d+[A-Z]?)?)\s+(.+?)\s*$", address or "", re.I)
    if not match:
        return None, None
    return match.group(1), match.group(2).upper()


def bis_profile_url(address, borough="1"):
    house_no, street = split_address(address)
    if not house_no:
        return ""
    query = urlencode({
        "boro": borough,
        "houseno": house_no,
        "street": street,
        "go2": " GO ",
        "requestid": "0",
    })
    return f"https://a810-bisweb.nyc.gov/bisweb/PropertyProfileOverviewServlet?{query}"


def bis_bbl_building_map_url(bbl, borough="1"):
    """Return the BIS building-on-lot map URL for a 10-digit BBL."""
    value = str(bbl or "").strip()
    if len(value) != 10 or not value.isdigit():
        return ""
    query = urlencode({
        "requestid": "1",
        "allborough": borough,
        "allblock": str(int(value[1:6])),
        "alllot": str(int(value[6:])),
    })
    return f"https://a810-bisweb.nyc.gov/bisweb/PropertyBrowseByBBLServlet?{query}"


def export_queue(targets_path, output_path, borough="1"):
    rows = []
    with Path(targets_path).open(newline="", encoding="utf-8") as handle:
        for source in csv.DictReader(handle):
            address = source.get("address", "")
            row = {field: source.get(field, "") for field in FIELDS}
            row["bis_property_profile_url"] = bis_profile_url(address, borough)
            row["bis_bbl_building_map_url"] = bis_bbl_building_map_url(
                source.get("resolved_bbl", ""), borough,
            )
            row["dob_now_public_portal_url"] = DOB_NOW_PUBLIC_PORTAL
            row["review_status"] = "unreviewed"
            if not row["bis_property_profile_url"]:
                row["review_status"] = "unparseable_address"
            rows.append(row)
    rows.sort(key=lambda row: (row["property"], row["address"]))
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--borough", default="1",
        help="DOB borough code used by the BIS address form (default: Manhattan, 1)",
    )
    args = parser.parse_args()
    rows = export_queue(args.targets, args.out, args.borough)
    print(f"wrote {len(rows)} review targets to {args.out}")


if __name__ == "__main__":
    main()
