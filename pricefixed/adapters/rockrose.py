"""Rockrose's official NYC building pages and their explicit selected listings."""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from hashlib import sha256
from html import unescape
from urllib.parse import quote, urljoin

from ..core import SourceAdapter, fetch


RESIDENTIAL_URL = "https://rockrose.com/residential/"
DOB_NOW_URL = "https://data.cityofnewyork.us/resource/w9ak-ipjd.json"
DOB_SELECT = (
    "job_filing_number,filing_status,house_no,street_name,borough,block,lot,bbl,bin,"
    "work_on_floor,apt_condo_no_s,filing_date,current_status_date,approved_date,"
    "signoff_date,job_type,job_description,existing_dwelling_units,"
    "proposed_dwelling_units,postcode"
)


def _text(value: str) -> str:
    value = re.sub(r"<br\s*/?>", " ", value or "", flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    return " ".join(unescape(value).split())


def _number(value: str | None):
    match = re.search(r"[\d,]+(?:\.\d+)?", value or "")
    return float(match.group(0).replace(",", "")) if match else None


def _beds_baths(value: str):
    text = value or ""
    beds = 0 if re.search(r"studio", text, re.I) else None
    bed_match = re.search(r"(\d+)\s+bed", text, re.I)
    if bed_match:
        beds = int(bed_match.group(1))
    bath_match = re.search(r"(\d+(?:\.\d+)?)\s+bath", text, re.I)
    return beds, float(bath_match.group(1)) if bath_match else None


def building_urls(html: str, source_url: str = RESIDENTIAL_URL) -> list[str]:
    """Return unique official Rockrose NYC building pages."""
    urls = []
    for href in re.findall(r"href=[\"']([^\"']*?/building/[^\"']+)[\"']", html, re.I):
        url = urljoin(source_url, unescape(href).split("#", 1)[0]).rstrip("/")
        if url not in urls:
            urls.append(url)
    return urls


def _address_key(value: str) -> str:
    value = value.upper()
    for old, new in (
        ("STREET", "ST"), ("AVENUE", "AVE"), ("BOULEVARD", "BLVD"),
        ("TERRACE", "TER"), ("PLACE", "PL"), ("ROAD", "RD"),
        ("DRIVE", "DR"), ("COURT", "CT"), ("CIRCLE", "CIR"),
        ("WEST", "W"), ("EAST", "E"), ("NORTH", "N"), ("SOUTH", "S"),
    ):
        value = value.replace(old, new)
    value = re.sub(r"\b(\d+)(?:ST|ND|RD|TH)\b", r"\1", value)
    return re.sub(r"[^A-Z0-9]", "", value)


def _dob_crosswalk(address: str, retrieved_at: str):
    """Return one exact official DOB NOW BBL, or no claim if ambiguous/missing."""
    house = re.match(r"^([\w-]+)\s+", address.strip())
    if not house:
        return None, None
    where = f"upper(house_no)='{house.group(1).upper().replace(chr(39), chr(39) * 2)}'"
    query = f"{DOB_NOW_URL}?$select={quote(DOB_SELECT)}&$where={quote(where)}&$limit=500"
    try:
        rows = json.loads(fetch(query, timeout=30))
    except Exception:
        return None, {"source": "dob_now_job_filings", "source_url": query,
                      "retrieved_at": retrieved_at, "rows": [], "error": "request_failed"}
    exact = [
        row for row in rows
        if _address_key(f"{row.get('house_no', '')} {row.get('street_name', '')}")
        == _address_key(address)
    ]
    bbls = sorted({str(row.get("bbl")) for row in exact if row.get("bbl")})
    evidence = {
        "source": "dob_now_job_filings",
        "source_url": query,
        "retrieved_at": retrieved_at,
        "rows": exact,
    }
    return (bbls[0] if len(bbls) == 1 else None), evidence


def parse_building_page(html: str, building_url: str, retrieved_at: str | None = None,
                        crosswalk_fn=None) -> list[dict]:
    """Extract only explicit selected-listing cards from one official building page."""
    retrieved_at = retrieved_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    street_match = re.search(
        r'<span class="property-details__street">\s*(.*?)\s*</span>', html, re.I | re.S
    )
    city_match = re.search(
        r'<span class="property-details__city-state-zip">\s*(.*?)\s*</span>', html, re.I | re.S
    )
    address = _text(street_match.group(1)) if street_match else ""
    source_address = f"{address}, {_text(city_match.group(1))}" if city_match else address
    name_match = re.search(r'<h1[^>]*id="HeroFancyTitle"[^>]*>\s*(.*?)\s*</h1>', html, re.I | re.S)
    building_name = _text(name_match.group(1)) if name_match else building_url.rstrip("/").rsplit("/", 1)[-1]
    crosswalk_fn = crosswalk_fn or _dob_crosswalk
    bbl, bbl_evidence = crosswalk_fn(address, retrieved_at) if address else (None, None)
    page_hash = sha256(html.encode("utf-8")).hexdigest()

    rows = []
    seen = set()
    card_pattern = re.compile(
        r'<div class=["\']grid-card__listing-card\b.*?'
        r'data-popup-unit-number=["\']([^"\']+)["\']', re.I | re.S
    )
    for match in card_pattern.finditer(html):
        unit = _text(match.group(1)).lstrip("#")
        if not unit or unit in seen:
            continue
        card = match.group(0)
        details_match = re.search(r'href=["\']([^"\']*/listing/[^"\']+)["\']', card, re.I)
        size_match = re.search(r"<li class=[\"']size[\"']>(.*?)</li>", card, re.I | re.S)
        price_match = re.search(r"<li class=[\"']price[\"']>(.*?)</li>", card, re.I | re.S)
        card_address = re.findall(r"<span class=[\"']address[\"']>(.*?)</span>", card, re.I | re.S)
        size = _text(size_match.group(1)) if size_match else ""
        bedrooms, bathrooms = _beds_baths(size)
        seen.add(unit)
        rows.append({
            "source_id": f"rr-{building_url.rstrip('/').rsplit('/', 1)[-1]}-{unit}",
            "building_name": building_name,
            "address": address,
            "unit_number": unit,
            "bedrooms": bedrooms,
            "bathrooms": bathrooms,
            "price": _number(_text(price_match.group(1))) if price_match else None,
            "sqft": None,
            "available_date": None,
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
            "raw_json": json.dumps({
                "source_url": building_url,
                "listing_url": urljoin(building_url, details_match.group(1)) if details_match else None,
                "source_address": source_address,
                "card_address": [_text(value) for value in card_address],
                "size_text": size,
                "price_text": _text(price_match.group(1)) if price_match else None,
                "retrieved_at": retrieved_at,
                "page_sha256": page_hash,
                "extraction_method": "official_rockrose_html_selected_listing",
                "bbl": bbl,
                "bbl_evidence": bbl_evidence,
            }, sort_keys=True),
        })
    return rows


class RockroseAdapter(SourceAdapter):
    name = "rockrose"
    description = "Rockrose — official NYC building pages with explicit selected listings"

    def pull(self) -> list[dict]:
        retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        index_html = fetch(RESIDENTIAL_URL, timeout=30)
        urls = building_urls(index_html, RESIDENTIAL_URL)
        rows = []
        for url in urls:
            try:
                rows.extend(parse_building_page(fetch(url, timeout=30), url, retrieved_at))
            except Exception as exc:  # noqa: BLE001 — preserve other properties
                print(f"  {url}: ERROR — {exc}")
            time.sleep(0.2)
        print(f"  Rockrose: {len(rows)} explicit listing rows from {len(urls)} building pages")
        return rows
