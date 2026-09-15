"""Olnick Rentals' public current NYC apartment availability pages."""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urljoin

from ..core import SourceAdapter, fetch


RENTALS_URL = "https://olnickrentals.com/"
BRONX_ADDRESSES = {"3333 Henry Hudson Pkwy", "2500 Johnson Avenue"}


def _text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return " ".join(unescape(value).replace("\xa0", " ").split())


def project_urls(html: str, source_url: str = RENTALS_URL) -> list[str]:
    """Return the explicit official rental-project pages from the index."""
    urls = []
    for href in re.findall(
        r'<a\b[^>]*class=["\'][^"\']*\bproject-item\b[^"\']*["\'][^>]*href=["\']([^"\']+)',
        html,
        re.I,
    ):
        url = urljoin(source_url, unescape(href).split("#", 1)[0])
        if url not in urls:
            urls.append(url)
    return urls


def _parse_name(value: str):
    """Return building, street, and explicit apartment label from one row name."""
    value = _text(value)
    match = re.match(r"^(.*?)\s*[–]\s*(.+?)\s*[–]\s*Apt\s+#?\s*([\w-]+)$", value, re.I)
    if not match:
        match = re.match(r"^(.*?)\s+-\s+(.+?)\s+-\s+Apt\s+#?\s*([\w-]+)$", value, re.I)
    if not match:
        return None
    building = re.sub(r"\s*[-–]+\s*$", "", match.group(1)).strip()
    address = match.group(2).strip()
    unit = match.group(3).strip()
    if not re.match(r"^\d[\d-]*\s+\S+", address) or not unit:
        return None
    return building, address, unit


def _number(value: str, integer: bool = False):
    match = re.search(r"[\d,]+(?:\.\d+)?", value or "")
    if not match:
        return None
    number = float(match.group(0).replace(",", ""))
    return int(number) if integer else number


def parse_project_page(
    html: str,
    source_url: str,
    retrieved_at: str | None = None,
) -> list[dict]:
    """Parse explicit address/unit rows from one official project page."""
    rows = []
    for name_match in re.finditer(r'<div\b[^>]*class=["\'][^"\']*\bname\b[^"\']*["\'][^>]*>(.*?)</div>', html, re.I | re.S):
        parsed = _parse_name(name_match.group(1))
        if not parsed:
            continue
        building, address, unit_number = parsed
        next_item = re.search(r'<div\b[^>]*class=["\'][^"\']*\bapartment-item\b', html[name_match.end():], re.I)
        tail_end = name_match.end() + (next_item.start() if next_item else 1800)
        tail = html[name_match.end():tail_end]
        params = [_text(value) for value in re.findall(r'<div\b[^>]*class=["\'][^"\']*\bitem\b[^"\']*["\'][^>]*>(.*?)</div>', tail, re.I | re.S)]
        detail_match = re.search(r'href=["\']([^"\']+)["\']', tail, re.I)
        detail_url = urljoin(source_url, unescape(detail_match.group(1))) if detail_match else None
        bedroom_text = params[0] if params else ""
        bedrooms = 0 if re.search(r"studio", bedroom_text, re.I) else _number(bedroom_text, integer=True)
        bathrooms = _number(bedroom_text, integer=False)
        sqft = _number(params[1], integer=True) if len(params) > 1 else None
        price = _number(params[2], integer=False) if len(params) > 2 else None
        raw = {
            "source_url": source_url,
            "unit_detail_url": detail_url,
            "building_name": building,
            "address": address,
            "unit_number": unit_number,
            "params": params,
            "retrieved_at": retrieved_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
        detail_id = detail_url.rsplit("/u/", 1)[-1].split("?", 1)[0] if detail_url and "/u/" in detail_url else None
        rows.append(
            {
                "source_id": f"olnick-{detail_id or address + '-' + unit_number}",
                "building_name": building,
                "address": address,
                "unit_number": unit_number,
                "bedrooms": bedrooms,
                "bathrooms": bathrooms,
                "price": price,
                "sqft": sqft,
                "available_date": None,
                "lease_terms": None,
                "amenities": None,
                "description": None,
                "floor_plan_url": None,
                "image_urls": None,
                "latitude": None,
                "longitude": None,
                "neighborhood": None,
                "borough": "Bronx" if address in BRONX_ADDRESSES else "Manhattan",
                "zipcode": None,
                "is_flex": 0,
                "is_rent_stabilized": 0,
                "finish_level": None,
                "raw_json": json.dumps(raw, sort_keys=True),
            }
        )
    return rows


class OlnickAdapter(SourceAdapter):
    name = "olnick"
    description = "Olnick Rentals — official public current apartment availability"

    def pull(self) -> list[dict]:
        retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        index_html = fetch(RENTALS_URL, timeout=30)
        rows = []
        urls = project_urls(index_html, RENTALS_URL)
        for url in urls:
            try:
                rows.extend(parse_project_page(fetch(url, timeout=30), url, retrieved_at))
            except Exception as exc:  # noqa: BLE001 — preserve other projects
                print(f"  {url}: ERROR — {exc}")
            time.sleep(0.2)
        print(f"  Olnick Rentals: {len(rows)} listings from {len(urls)} explicit project pages")
        return rows
