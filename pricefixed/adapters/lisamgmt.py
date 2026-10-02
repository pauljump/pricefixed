"""Lisa Management's public Next.js residential availability feed."""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

from ..core import SourceAdapter, fetch


RESIDENTIAL_URL = "https://www.lisamgmt.com/residential"


def _next_data(html: str) -> dict:
    match = re.search(r'<script\s+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, re.I | re.S)
    if not match:
        return {}
    return json.loads(match.group(1))


def _number(value, integer: bool = False):
    match = re.search(r"[\d,]+(?:\.\d+)?", str(value or ""))
    if not match:
        return None
    number = float(match.group(0).replace(",", ""))
    return int(number) if integer else number


def parse_residential_page(
    html: str,
    source_url: str = RESIDENTIAL_URL,
    retrieved_at: str | None = None,
) -> tuple[list[dict], int]:
    """Parse exact-address apartment records and return (rows, page count)."""
    page_props = (_next_data(html).get("props") or {}).get("pageProps") or {}
    apartments = page_props.get("apartments") or []
    page_count = int(page_props.get("pagesNumber") or 1)
    observed_at = retrieved_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rows = []
    for item in apartments:
        prop = item.get("property") or {}
        address = str(prop.get("address") or "").strip()
        unit_number = str(item.get("unitNumber") or "").strip()
        state = str(prop.get("state") or "").upper()
        if state and state != "NY":
            continue
        if not re.match(r"^\d[\d-]*\s+\S+", address) or not unit_number:
            continue
        bedrooms_text = str(item.get("bedrooms") or "")
        bedrooms = 0 if re.search(r"studio", bedrooms_text, re.I) else _number(bedrooms_text, integer=True)
        raw = {
            "source_url": source_url,
            "retrieved_at": observed_at,
            "api_item": item,
        }
        rows.append(
            {
                "source_id": f"lisamgmt-{item.get('id') or address + '-' + unit_number}",
                "building_name": str(prop.get("name") or "").strip(),
                "address": address,
                "unit_number": unit_number,
                "bedrooms": bedrooms,
                "bathrooms": _number(item.get("bathrooms"), integer=False),
                "price": float(item["rent"]) if item.get("rent") not in (None, "") else None,
                "sqft": item.get("squareFeet"),
                "available_date": None,
                "lease_terms": None,
                "amenities": None,
                "description": None,
                "floor_plan_url": None,
                "image_urls": json.dumps([item["image"]]) if item.get("image") else None,
                "latitude": prop.get("latitude"),
                "longitude": prop.get("longitude"),
                "neighborhood": (prop.get("neighborhood") or {}).get("name"),
                "borough": prop.get("city"),
                "zipcode": prop.get("zip"),
                "is_flex": 0,
                "is_rent_stabilized": 0,
                "finish_level": None,
                "raw_json": json.dumps(raw, sort_keys=True, default=str),
            }
        )
    return rows, page_count


class LisaManagementAdapter(SourceAdapter):
    name = "lisamgmt"
    description = "Lisa Management — official public residential apartment feed"

    def pull(self) -> list[dict]:
        retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        rows = []
        first_html = fetch(RESIDENTIAL_URL, timeout=30)
        first_rows, page_count = parse_residential_page(first_html, RESIDENTIAL_URL, retrieved_at)
        rows.extend(first_rows)
        for page in range(2, page_count + 1):
            url = f"{RESIDENTIAL_URL}?{urlencode({'page': page})}"
            try:
                page_rows, _ = parse_residential_page(fetch(url, timeout=30), url, retrieved_at)
                rows.extend(page_rows)
            except Exception as exc:  # noqa: BLE001 — preserve page-one rows
                print(f"  page {page}: ERROR — {exc}")
            time.sleep(0.2)
        print(f"  Lisa Management: {len(rows)} listings across {page_count} public pages")
        return rows
