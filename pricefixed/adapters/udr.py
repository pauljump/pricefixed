"""UDR's official NYC apartment-pricing pages with explicit unit JSON-LD."""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urljoin

from ..core import SourceAdapter, fetch
from .rockrose import _dob_crosswalk


INDEX_URL = "https://www.udr.com/new-york-city-apartments/"


def _text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return " ".join(unescape(value).split())


def pricing_urls(html: str, source_url: str = INDEX_URL) -> list[str]:
    urls = []
    for href in re.findall(r"href=[\"']([^\"']*/apartments-pricing/)[\"']", html, re.I):
        url = urljoin(source_url, unescape(href))
        if url not in urls:
            urls.append(url)
    return urls


def _address(html: str) -> str:
    match = re.search(
        r'<span class="prop-address">\s*<span>(.*?)</span>.*?'
        r'<span>(.*?)</span>.*?<span>(.*?)</span>.*?<span>(\d{5})</span>\s*</span>',
        html, re.I | re.S,
    )
    if match:
        street, city, state, zipcode = (_text(value) for value in match.groups())
        return f"{street}, {city}, {state} {zipcode}"
    match = re.search(r'<span class="prop-address">(.*?)</span>', html, re.I | re.S)
    return _text(match.group(1)) if match else ""


def parse_pricing_page(html: str, source_url: str, retrieved_at: str | None = None,
                       crosswalk_fn=None) -> list[dict]:
    """Parse only JSON-LD items whose name contains an explicit apartment label."""
    retrieved_at = retrieved_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    source_address = _address(html)
    address = source_address.split(",", 1)[0].strip()
    crosswalk_fn = crosswalk_fn or _dob_crosswalk
    bbl, bbl_evidence = crosswalk_fn(address, retrieved_at) if address else (None, None)
    zipcode_match = re.search(r"\b(\d{5})\b", source_address)
    zipcode = zipcode_match.group(1) if zipcode_match else None
    rows = []
    seen = set()
    for raw_script in re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.I | re.S,
    ):
        try:
            data = json.loads(raw_script)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        for entry in data.get("itemListElement") or []:
            item = entry.get("item") if isinstance(entry, dict) else None
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "")
            match = re.search(r"^Apartment\s+#\S+\s+-\s*(\S+)$", name, re.I)
            if not match:
                continue
            unit = match.group(1).strip()
            offer = item.get("offers") or {}
            unit_url = str(item.get("url") or offer.get("url") or source_url)
            source_id_match = re.search(r"[?&]unitid=([^&]+)", unit_url, re.I)
            unit_id = source_id_match.group(1) if source_id_match else unit
            if unit_id in seen or not address:
                continue
            seen.add(unit_id)
            slug = source_url.rstrip("/").rsplit("/", 2)[-2]
            rows.append({
                "source_id": f"udr-{slug}-{unit_id}",
                "building_name": slug.replace("-", " ").title(),
                "address": address,
                "unit_number": unit,
                "bedrooms": item.get("numberOfBedrooms"),
                "bathrooms": item.get("numberOfBathroomsTotal"),
                "price": offer.get("price"),
                "sqft": (item.get("floorSize") or {}).get("value"),
                "available_date": None,
                "lease_terms": None,
                "amenities": None,
                "description": item.get("description"),
                "floor_plan_url": urljoin(source_url, item.get("image")) if item.get("image") else None,
                "image_urls": None,
                "latitude": None,
                "longitude": None,
                "neighborhood": None,
                "borough": "Manhattan",
                "zipcode": zipcode,
                "is_flex": 0,
                "is_rent_stabilized": 0,
                "finish_level": None,
                "raw_json": json.dumps({
                    "source_url": source_url,
                    "source_address": source_address,
                    "bbl": bbl,
                    "bbl_evidence": bbl_evidence,
                    "resolved_street_address": address,
                    "unit_jsonld": item,
                    "retrieved_at": retrieved_at,
                    "extraction_method": "official_udr_apartment_jsonld",
                }, sort_keys=True, default=str),
            })
    return rows


class UDRAdapter(SourceAdapter):
    name = "udr"
    description = "UDR — official NYC apartment-pricing JSON-LD pages"

    def pull(self) -> list[dict]:
        retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        index_html = fetch(INDEX_URL, timeout=30)
        urls = pricing_urls(index_html, INDEX_URL)
        rows = []
        for url in urls:
            try:
                rows.extend(parse_pricing_page(fetch(url, timeout=30), url, retrieved_at))
            except Exception as exc:  # noqa: BLE001 — preserve other communities
                print(f"  {url}: ERROR — {exc}")
            time.sleep(0.2)
        print(f"  UDR: {len(rows)} explicit unit JSON-LD rows from {len(urls)} pricing pages")
        return rows
