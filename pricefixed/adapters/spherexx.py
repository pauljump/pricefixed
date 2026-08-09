"""Spherexx / AdKast public availability pages.

Several NYC operators publish current availability through the same public
Spherexx page shape. The page's AJAX response contains the manager's building
name, exact street address, apartment label, and current asking terms. This is
listing evidence only: it is never expanded into an apartment roster.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urlencode, urljoin, urlparse

from ..core import SourceAdapter, fetch


PORTALS = [
    {
        "label": "Marquis Apartments",
        "url": "https://www.marquisapts.com/availability/",
        "page_path": "/availability/",
    },
    {
        "label": "Kings & Queens Apartments (Brooklyn page)",
        "url": "https://www.kingsqueensapts.com/brooklyn/available-rentals-nyc/",
        "page_path": "/brooklyn/available-rentals-nyc/",
    },
]


def _text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return " ".join(unescape(value).split())


def _number(value: str | None, integer: bool = True):
    if not value:
        return None
    cleaned = re.sub(r"[^0-9.]", "", value)
    if not cleaned:
        return None
    try:
        return int(float(cleaned)) if integer else float(cleaned)
    except ValueError:
        return None


def _unit_rows(html: str, portal: dict, source_url: str, feed_url: str, retrieved_at: str) -> list[dict]:
    rows = []
    for row in re.findall(
        r'<div\s+class="unit-list-item\b.*?</button>\s*</div>\s*</div>',
        html,
        flags=re.I | re.DOTALL,
    ):
        uid_m = re.search(r'data-uid="([^"]+)"', row, re.I)
        link_m = re.search(r'data-url="([^"]+)"', row, re.I)
        building_m = re.search(r'data-building-name="([^"]+)"', row, re.I)
        address_m = re.search(
            r'class="[^"]*\bunit-list-address\b[^"]*"[^>]*>\s*<nobr>(.*?)</nobr>', row, re.I | re.DOTALL
        )
        unit_m = re.search(r'aria-label="([^"]+?)\s+in\s+', row, re.I)
        beds_m = re.search(r'aria-label="[^"]*?,\s*(Studio|\d+\s+Bedrooms?)\s+', row, re.I)
        baths_m = re.search(
            r'aria-label="[^"]*?,\s*(?:Studio|\d+\s+Bedrooms?)\s+(\d+(?:\.\d+)?)\s+Bathrooms?',
            row,
            re.I,
        )
        sqft_m = re.search(
            r'aria-label="[^"]*?,\s*(?:Studio|\d+\s+Bedrooms?)\s+\d+(?:\.\d+)?\s+Bathrooms?,\s*([\d,]+)\s+square feet',
            row,
            re.I,
        )
        date_m = re.search(
            r'class="[^"]*\bunit-date-available\b[^"]*"[^>]*>([^<]+)', row, re.I
        )
        price_m = re.search(r'data-base-price="([^"]+)"', row, re.I)
        if not (uid_m and building_m and address_m and unit_m):
            continue

        unit_number = _text(unit_m.group(1))
        address = _text(address_m.group(1))
        beds_value = beds_m.group(1).strip().lower() if beds_m else None
        bedrooms = 0 if beds_value == "studio" else _number(beds_value, integer=True)
        raw = {
            "unit_id": uid_m.group(1),
            "unit_url": urljoin(source_url, link_m.group(1)) if link_m else None,
            "building_name": _text(building_m.group(1)),
            "address": address,
            "unit_number": unit_number,
            "bedrooms": bedrooms,
            "bathrooms": _number(baths_m.group(1), integer=False) if baths_m else None,
            "sqft": _number(sqft_m.group(1)) if sqft_m else None,
            "price": _number(price_m.group(1)) if price_m else None,
            "available_date": _text(date_m.group(1)) if date_m else None,
            "source_url": source_url,
            "feed_url": feed_url,
            "retrieved_at": retrieved_at,
        }
        rows.append(
            {
                "source_id": f"spherexx-{urlparse(source_url).hostname}-{uid_m.group(1)}",
                "building_name": raw["building_name"],
                "address": address,
                "unit_number": unit_number,
                "bedrooms": bedrooms,
                "bathrooms": raw["bathrooms"],
                "price": raw["price"],
                "sqft": raw["sqft"],
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


class SpherexxAdapter(SourceAdapter):
    name = "spherexx"
    description = "Spherexx/AdKast — public unit availability pages for confirmed NYC portals"
    PORTALS = PORTALS
    PAGE_SIZE = 10
    MAX_PAGES = 100

    @staticmethod
    def _payload(page: int) -> bytes:
        return urlencode(
            {
                "bedrooms": "",
                "priceMin": "1000",
                "isDefaultMinPrice": "true",
                "priceMax": "20000",
                "buildings": "",
                "moveInDate": "",
                "availableNowOnly": "0",
                "page": str(page),
                "lastNum": "",
                "sort": "",
                "numberPerPage": str(SpherexxAdapter.PAGE_SIZE),
            }
        ).encode()

    def _fetch_portal(self, portal: dict) -> list[dict]:
        retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        feed_url = urljoin(portal["url"], "/ajax/getunitlist.asp")
        all_rows = []
        seen_ids = set()
        for page in range(1, self.MAX_PAGES + 1):
            html = fetch(
                feed_url,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "Referer": portal["url"],
                    "X-Requested-With": "XMLHttpRequest",
                },
                data=self._payload(page),
                method="POST",
                timeout=30,
            )
            rows = _unit_rows(html, portal, portal["url"], feed_url, retrieved_at)
            fresh = [row for row in rows if row["source_id"] not in seen_ids]
            all_rows.extend(fresh)
            seen_ids.update(row["source_id"] for row in fresh)
            if len(rows) < self.PAGE_SIZE:
                break
        return all_rows

    def pull(self) -> list[dict]:
        all_units = []
        for portal in self.PORTALS:
            try:
                units = self._fetch_portal(portal)
                print(f"  {portal['label']}: {len(units)} listings")
                all_units.extend(units)
            except Exception as exc:  # noqa: BLE001 — preserve other portals
                print(f"  {portal['label']}: ERROR — {exc}")
            time.sleep(0.25)
        return all_units
