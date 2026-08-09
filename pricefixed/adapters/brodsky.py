"""Brodsky Organization public current rental listings."""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urljoin

from ..core import SourceAdapter, fetch


RENTALS_URL = "https://www.brodsky.com/rentals"


def _text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return " ".join(unescape(value).split())


def _number(value: str | None, integer: bool = False):
    if not value:
        return None
    match = re.search(r"[\d,]+(?:\.\d+)?", value)
    if not match:
        return None
    parsed = float(match.group(0).replace(",", ""))
    return int(parsed) if integer else parsed


def listing_urls(html: str, source_url: str = RENTALS_URL) -> list[str]:
    """Return explicit current apartment links from the official rentals page."""
    urls = []
    for href in re.findall(r"href=[\"']([^\"']*?/rentals/[^\"']*?apartment-[^\"']+)[\"']", html, re.I):
        url = urljoin(source_url, unescape(href).split("#", 1)[0])
        if url not in urls:
            urls.append(url)
    return urls


def parse_listing_page(html: str, source_url: str) -> dict | None:
    matches = re.findall(
        r'<script\s+type="application/ld\+json"[^>]*>(.*?)</script>',
        html,
        flags=re.I | re.DOTALL,
    )
    listing = None
    for raw_json in matches:
        try:
            candidate = json.loads(raw_json)
        except json.JSONDecodeError:
            continue
        if candidate.get("@type") == "RealEstateListing" and candidate.get("mainEntity"):
            listing = candidate
            break
    if not listing:
        return None

    address_obj = listing.get("address") or listing["mainEntity"].get("address") or {}
    address_with_unit = str(address_obj.get("streetAddress") or "").strip()
    unit_match = re.search(r",\s*(?:Unit|Apt\.?|Apartment)\s*([\w-]+)\s*$", address_with_unit, re.I)
    unit_number = unit_match.group(1) if unit_match else str(listing["mainEntity"].get("name") or "").strip()
    address = address_with_unit[:unit_match.start()].strip() if unit_match else address_with_unit
    if not address or not unit_number:
        return None

    bedroom_match = re.search(r'\\+"bedrooms\\+":\\+"([^"\\]+)', html, re.I)
    bathroom_match = re.search(r'\\+"bathrooms\\+":\\+"([^"\\]+)', html, re.I)
    available_match = re.search(r'\\+"availableDate\\+":\\+"([^"\\]+)', html, re.I)
    bedroom_text = bedroom_match.group(1) if bedroom_match else ""
    bedrooms = 0 if re.search(r"studio", bedroom_text, re.I) else _number(bedroom_text, integer=True)
    offer = listing.get("offers") or {}
    raw = {
        "source_url": source_url,
        "listing_jsonld": listing,
        "bedroom_text": bedroom_text or None,
        "bathroom_text": bathroom_match.group(1) if bathroom_match else None,
        "available_date": available_match.group(1) if available_match else None,
        "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    return {
        "source_id": f"brodsky-{source_url.rstrip('/').rsplit('/', 1)[-1]}",
        "building_name": str(listing.get("name") or "").split(" - Apartment", 1)[0].strip(),
        "address": address,
        "unit_number": unit_number,
        "bedrooms": bedrooms,
        "bathrooms": _number(bathroom_match.group(1), integer=False) if bathroom_match else None,
        "price": offer.get("price"),
        "sqft": None,
        "available_date": raw["available_date"] or offer.get("availability"),
        "lease_terms": None,
        "amenities": None,
        "description": listing.get("description"),
        "floor_plan_url": None,
        "image_urls": json.dumps(listing.get("image")) if listing.get("image") else None,
        "latitude": None,
        "longitude": None,
        "neighborhood": None,
        "borough": address_obj.get("addressLocality"),
        "zipcode": address_obj.get("postalCode"),
        "is_flex": 0,
        "is_rent_stabilized": 0,
        "finish_level": None,
        "raw_json": json.dumps(raw, sort_keys=True, default=str),
    }


class BrodskyAdapter(SourceAdapter):
    name = "brodsky"
    description = "Brodsky Organization — official current apartment detail pages"

    def pull(self) -> list[dict]:
        index_html = fetch(RENTALS_URL, timeout=30)
        urls = listing_urls(index_html, RENTALS_URL)
        rows = []
        for url in urls:
            try:
                row = parse_listing_page(fetch(url, timeout=30), url)
                if row:
                    rows.append(row)
            except Exception as exc:  # noqa: BLE001 — preserve other listings
                print(f"  {url}: ERROR — {exc}")
            time.sleep(0.2)
        print(f"  Brodsky Organization: {len(rows)} listings from {len(urls)} explicit links")
        return rows
