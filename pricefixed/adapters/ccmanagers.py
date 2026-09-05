"""C+C Apartment Management's public current-availability table."""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urljoin

from ..core import SourceAdapter, fetch


AVAILABILITY_URL = "https://ccmanagers.com/availability/"


def _text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return " ".join(unescape(value).split())


def _money(value: str):
    match = re.search(r"[\d,]+(?:\.\d+)?", value or "")
    return float(match.group(0).replace(",", "")) if match else None


def parse_availability(html: str, source_url: str = AVAILABILITY_URL) -> list[dict]:
    rows = []
    for row_html in re.findall(r"<tr\b.*?</tr>", html, flags=re.I | re.DOTALL):
        cells = re.findall(r"<td\b.*?</td>", row_html, flags=re.I | re.DOTALL)
        if len(cells) < 6:
            continue
        address = _text(cells[0])
        unit = _text(cells[1])
        if not address or not unit or address.lower() == "building" or unit.lower() == "unit":
            continue
        building_href = re.search(r"href=[\"']([^\"']+)[\"']", cells[0], re.I)
        unit_href = re.search(r"href=[\"']([^\"']+)[\"']", cells[1], re.I)
        unit_url = urljoin(source_url, unescape(unit_href.group(1))) if unit_href else None
        source_key = unit_url or f"{address}|{unit}"
        bedrooms = _money(_text(cells[2]))
        bathrooms = _money(_text(cells[3]))
        raw = {
            "building_url": urljoin(source_url, unescape(building_href.group(1))) if building_href else None,
            "unit_url": unit_url,
            "address": address,
            "unit_number": unit,
            "bedrooms": int(bedrooms) if bedrooms is not None else None,
            "bathrooms": bathrooms,
            "rent": _money(_text(cells[4])),
            "available_date": _text(cells[5]),
            "source_url": source_url,
        }
        rows.append(
            {
                "source_id": f"ccmanagers-{source_key}",
                "building_name": address,
                "address": address,
                "unit_number": unit,
                "bedrooms": raw["bedrooms"],
                "bathrooms": raw["bathrooms"],
                "price": raw["rent"],
                "sqft": None,
                "available_date": raw["available_date"],
                "lease_terms": None,
                "amenities": None,
                "description": None,
                "floor_plan_url": None,
                "image_urls": None,
                "latitude": None,
                "longitude": None,
                "neighborhood": None,
                "borough": None,
                "zipcode": None,
                "is_flex": 0,
                "is_rent_stabilized": 0,
                "finish_level": None,
                "raw_json": json.dumps(raw, sort_keys=True),
            }
        )
    return rows


class CCManagersAdapter(SourceAdapter):
    name = "ccmanagers"
    description = "C+C Apartment Management — public current-availability table"

    def pull(self) -> list[dict]:
        retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        html = fetch(AVAILABILITY_URL, timeout=30)
        rows = parse_availability(html, AVAILABILITY_URL)
        for row in rows:
            raw = json.loads(row["raw_json"])
            raw["retrieved_at"] = retrieved_at
            row["raw_json"] = json.dumps(raw, sort_keys=True)
        print(f"  C+C Apartment Management: {len(rows)} listings")
        time.sleep(0.25)
        return rows
