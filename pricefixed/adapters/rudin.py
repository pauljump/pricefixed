"""Rudin Residential's public availability JSON.

The official Rudin availability page loads ``/api/properties-json``.  The
response contains both property records and explicit current listing records.
This adapter keeps only listing records whose parent property has an exact
street address; property/floor-plan records are never expanded into units.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urljoin

from ..core import SourceAdapter, fetch


class RudinAdapter(SourceAdapter):
    name = "rudin"
    description = "Rudin Residential public property/listing JSON"

    PAGE_URL = "https://www.rudinresidential.com/properties/availability"
    API_URL = "https://www.rudinresidential.com/api/properties-json"

    @staticmethod
    def _text(value):
        return " ".join(unescape(re.sub(r"<[^>]+>", " ", str(value or ""))).split())

    @classmethod
    def _available_date(cls, value):
        text = cls._text(value)
        match = re.search(r'datetime=["\']([^"\']+)', str(value or ""), re.I)
        return match.group(1) if match else text or None

    @classmethod
    def _parse_payload(cls, payload, page_url=None, api_url=None, retrieved_at=None):
        page_url = page_url or cls.PAGE_URL
        api_url = api_url or cls.API_URL
        retrieved_at = retrieved_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        properties = {
            str(item.get("nid")): item
            for item in payload
            if str(item.get("type") or "").lower() == "property"
            and cls._text(item.get("field_address"))
        }
        rows = []
        for listing in payload:
            if str(listing.get("type") or "").lower() != "listing":
                continue
            if str(listing.get("field_availability") or "").strip().lower() not in {"on", "1", "true"}:
                continue
            property_record = properties.get(str(listing.get("field_property")))
            if not property_record:
                continue
            unit_number = cls._text(listing.get("title"))
            address = cls._text(property_record.get("field_address"))
            if not unit_number or not address or not listing.get("nid"):
                continue
            raw = {
                "source": cls.name,
                "source_url": page_url,
                "feed_url": api_url,
                "retrieved_at": retrieved_at,
                "property": property_record,
                "listing": listing,
            }
            rows.append({
                "source_id": f"rudin-{listing['nid']}",
                "building_name": property_record.get("title"),
                "address": address,
                "unit_number": unit_number,
                "bedrooms": cls._number(listing.get("field_bedrooms")),
                "bathrooms": cls._decimal(listing.get("field_bathrooms")),
                "price": cls._number(listing.get("field_maximum_rent")),
                "sqft": cls._number(listing.get("field_square_feet")),
                "available_date": cls._available_date(listing.get("field_availability_date")),
                "lease_terms": None,
                "amenities": cls._text(listing.get("field_amenities_section_items")) or None,
                "description": cls._text(listing.get("field_short_description")) or None,
                "floor_plan_url": urljoin(page_url, cls._image_url(listing.get("field_listing_floorplan"))),
                "image_urls": None,
                "latitude": property_record.get("field_latitude"),
                "longitude": property_record.get("field_longitude"),
                "neighborhood": property_record.get("field_neighborhood"),
                "borough": "Manhattan",
                "zipcode": None,
                "is_flex": 0,
                "is_rent_stabilized": 0,
                "finish_level": None,
                "raw_json": json.dumps(raw, default=str, sort_keys=True),
            })
        return rows

    @staticmethod
    def _number(value):
        if value is None or value == "":
            return None
        match = re.search(r"\d+(?:\.\d+)?", str(value).replace(",", ""))
        return int(float(match.group(0))) if match else None

    @staticmethod
    def _decimal(value):
        if value is None or value == "":
            return None
        match = re.search(r"\d+(?:\.\d+)?", str(value))
        return float(match.group(0)) if match else None

    @classmethod
    def _image_url(cls, value):
        match = re.search(r'(?:src|srcset)=["\']([^"\']+)', str(value or ""), re.I)
        return match.group(1) if match else ""

    def pull(self):
        retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        try:
            payload = json.loads(fetch(self.API_URL, timeout=45))
        except Exception as exc:  # noqa: BLE001 — keep source failure visible
            print(f"  Rudin availability JSON failed: {exc}")
            return []
        rows = self._parse_payload(payload, self.PAGE_URL, self.API_URL, retrieved_at)
        print(f"  {len(rows)} explicit available-unit rows")
        return rows
