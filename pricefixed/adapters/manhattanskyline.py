"""Manhattan Skyline Management's public current rental listings.

The public rentals page exposes a JSON unit feed, but the feed's building
address is sometimes blank. Each unit URL in that feed is therefore fetched
and accepted only when its own official detail page supplies a numeric street
address alongside the explicit apartment label from the API. Building names,
coordinates, and availability counts are never used to manufacture address or
unit identities.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from html import unescape

from ..core import SourceAdapter, fetch


RENTALS_URL = "https://manhattanskyline.com/rentals"
UNITS_URL = "https://manhattanskyline.com/api/units"


def _text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return " ".join(unescape(value).replace("\xa0", " ").split())


def _street_address(html: str) -> tuple[str | None, str | None]:
    """Extract the street and ZIP from the detail page's address element."""
    match = re.search(r"<address\b[^>]*>(.*?)</address>", html, re.I | re.S)
    if not match:
        return None, None
    parts = re.split(r"<br\s*/?>", match.group(1), flags=re.I)
    address = _text(parts[0]) if parts else ""
    location = _text(parts[1]) if len(parts) > 1 else ""
    zipcode_match = re.search(r"\b(\d{5}(?:-\d{4})?)\b", location)
    # A building name such as "Manhattan East" is not an exact street address.
    if not re.match(r"^\d[\d-]*\s+\S+", address):
        return None, zipcode_match.group(1) if zipcode_match else None
    return address, zipcode_match.group(1) if zipcode_match else None


def parse_unit_page(
    html: str,
    item: dict,
    source_url: str,
    api_url: str = UNITS_URL,
    retrieved_at: str | None = None,
) -> dict | None:
    """Map one API unit plus its official detail page to a listing row."""
    address, zipcode = _street_address(html)
    unit_number = str(item.get("number") or "").strip()
    if not address or not unit_number:
        return None

    building = item.get("building") or {}
    building_name = _text(str(building.get("name") or "")).strip()
    location = ((building.get("address") or {}).get("latLng") or {})
    images = [image.get("src") for image in item.get("card_images") or [] if image.get("src")]
    raw = {
        "source_url": source_url,
        "feed_url": api_url,
        "retrieved_at": retrieved_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "api_item": item,
    }
    return {
        "source_id": f"manhattanskyline-{item.get('slug') or unit_number}",
        "building_name": building_name,
        "address": address,
        "unit_number": unit_number,
        "bedrooms": item.get("bedrooms"),
        "bathrooms": item.get("bathrooms"),
        "price": float(item["price"]) if item.get("price") not in (None, "") else None,
        "sqft": item.get("square_footage"),
        "available_date": item.get("available_on"),
        "lease_terms": None,
        "amenities": None,
        "description": item.get("body"),
        "floor_plan_url": None,
        "image_urls": json.dumps(images) if images else None,
        "latitude": location.get("lat"),
        "longitude": location.get("lng"),
        "neighborhood": (building.get("neighborhood") or {}).get("name"),
        "borough": "Manhattan",
        "zipcode": zipcode,
        "is_flex": 0,
        "is_rent_stabilized": 0,
        "finish_level": None,
        "raw_json": json.dumps(raw, sort_keys=True, default=str),
    }


class ManhattanSkylineAdapter(SourceAdapter):
    name = "manhattanskyline"
    description = "Manhattan Skyline Management — public unit API plus official detail pages"

    def pull(self) -> list[dict]:
        retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        payload = json.loads(fetch(UNITS_URL, timeout=30))
        units = ((payload.get("units") or {}).get("data") or [])
        rows = []
        rejected = 0
        for item in units:
            source_url = str(item.get("url") or "").strip()
            if not source_url:
                rejected += 1
                continue
            try:
                row = parse_unit_page(
                    fetch(source_url, timeout=30),
                    item,
                    source_url,
                    api_url=UNITS_URL,
                    retrieved_at=retrieved_at,
                )
                if row:
                    rows.append(row)
                else:
                    rejected += 1
            except Exception as exc:  # noqa: BLE001 — preserve other listings
                rejected += 1
                print(f"  {source_url}: ERROR — {exc}")
            time.sleep(0.15)
        print(
            f"  Manhattan Skyline Management: {len(rows)} listings from "
            f"{len(units)} API rows ({rejected} rejected without exact address)"
        )
        return rows
