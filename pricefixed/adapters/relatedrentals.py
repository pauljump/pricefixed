"""Related Rentals' public NYC availability search.

The official search lists current availability by floor-plan category, while
each linked detail page carries the explicit apartment ID and exact property
address.  Only detail pages with both are emitted; search-card counts and
floor-plan names are never expanded into units.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urlencode, urljoin

from ..core import SourceAdapter, fetch
from .rockrose import _dob_crosswalk


class RelatedRentalsAdapter(SourceAdapter):
    name = "relatedrentals"
    description = "Related Rentals public NYC availability and unit detail pages"

    SEARCH_URL = "https://www.relatedrentals.com/search"
    CITY = "New York City"
    MAX_PAGES = 20

    @staticmethod
    def _text(value):
        return " ".join(unescape(re.sub(r"<[^>]+>", " ", str(value or ""))).split())

    @classmethod
    def _search_url(cls, page):
        return f"{cls.SEARCH_URL}?{urlencode({f'city[{cls.CITY}]': cls.CITY, 'page': page})}"

    @classmethod
    def _teasers(cls, html, page_url):
        rows = []
        for block in re.findall(
            r'<article\s+class="node\s+node--type-unit\b.*?</article>',
            html,
            flags=re.I | re.DOTALL,
        ):
            api_m = re.search(r'data-api-id="([^"]+)"', block, re.I)
            href_m = re.search(r'<a\s+href="([^"]+)"[^>]*class="field-group-link"', block, re.I)
            if not (api_m and href_m):
                continue
            rows.append({
                "api_id": api_m.group(1),
                "url": urljoin(page_url, unescape(href_m.group(1))),
                "price": re.search(r'data-price="([^"]+)"', block, re.I).group(1)
                if re.search(r'data-price="([^"]+)"', block, re.I) else None,
                "raw_teaser": block,
            })
        return rows

    @classmethod
    def _settings(cls, html):
        match = re.search(
            r'<script[^>]+type="application/json"[^>]+data-drupal-selector="drupal-settings-json"[^>]*>(.*?)</script>',
            html,
            flags=re.I | re.DOTALL,
        )
        return json.loads(match.group(1)) if match else {}

    @classmethod
    def _parse_detail(cls, html, source_url, teaser=None, retrieved_at=None,
                      bbl=None, bbl_evidence=None):
        teaser = teaser or {}
        retrieved_at = retrieved_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        settings = cls._settings(html)
        entity = settings.get("entity") or {}
        visited = settings.get("visited_node_info") or {}
        gtm = settings.get("gtmUnitDetail") or {}
        unit_id = cls._text(entity.get("unit_id"))
        property_name = cls._text(entity.get("unit_property_name"))
        address_match = re.search(
            r'class="fg-unit-header__property-label"[^>]*>.*?\|\s*([^<]+?)\s*</div>',
            html,
            flags=re.I | re.DOTALL,
        )
        address_text = cls._text(address_match.group(1)) if address_match else ""
        premise_match = re.match(r"(.+?)\s+New York,\s*NY\s+(\d{5})(?:-\d{4})?$", address_text, re.I)
        if not (unit_id and property_name and premise_match):
            return None
        address, zipcode = premise_match.groups()
        date_match = re.search(
            r'class="[^"]*unit-availability__value[^"]*"[^>]*>(.*?)</dd>',
            html,
            flags=re.I | re.DOTALL,
        )
        price = visited.get("availability_price") or teaser.get("price")
        raw = {
            "source": cls.name,
            "source_url": source_url,
            "retrieved_at": retrieved_at,
            "search_teaser": teaser,
            "entity": entity,
            "visited_node_info": visited,
            "gtm_unit_detail": gtm,
            "bbl": bbl,
            "bbl_evidence": bbl_evidence,
            "detail_html_sha256": hashlib.sha256(html.encode()).hexdigest(),
            "detail_html": html,
        }
        bedrooms = gtm.get("dimension6")
        bathrooms = gtm.get("dimension7")
        return {
            "source_id": f"related-{entity.get('id') or teaser.get('api_id')}",
            "building_name": property_name,
            "address": cls._text(address),
            "unit_number": unit_id,
            "bedrooms": cls._decimal(bedrooms),
            "bathrooms": cls._decimal(bathrooms),
            "price": cls._number(price),
            "sqft": None,
            "available_date": cls._text(date_match.group(1)) if date_match else None,
            "lease_terms": None,
            "amenities": None,
            "description": None,
            "floor_plan_url": None,
            "image_urls": None,
            "latitude": None,
            "longitude": None,
            "neighborhood": gtm.get("category"),
            "borough": "Manhattan" if "New York" in str(gtm.get("brand")) else None,
            "zipcode": zipcode,
            "is_flex": 0,
            "is_rent_stabilized": 0,
            "finish_level": None,
            "raw_json": json.dumps(raw, default=str, sort_keys=True),
        }

    @staticmethod
    def _number(value):
        match = re.search(r"\d+(?:\.\d+)?", str(value or "").replace(",", ""))
        return int(float(match.group(0))) if match else None

    @staticmethod
    def _decimal(value):
        match = re.search(r"\d+(?:\.\d+)?", str(value or ""))
        return float(match.group(0)) if match else None

    def pull(self):
        retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        teasers = []
        seen_ids = set()
        for page in range(self.MAX_PAGES):
            page_url = self._search_url(page)
            try:
                html = fetch(page_url, timeout=45)
            except Exception as exc:  # noqa: BLE001 — retain other page results
                print(f"  Related Rentals search page {page} failed: {exc}")
                break
            page_rows = self._teasers(html, page_url)
            fresh = [row for row in page_rows if row["api_id"] not in seen_ids]
            teasers.extend(fresh)
            seen_ids.update(row["api_id"] for row in fresh)
            if not page_rows or len(fresh) == 0:
                break
            time.sleep(0.05)

        def fetch_detail(teaser):
            try:
                return teaser, fetch(teaser["url"], timeout=45), None
            except Exception as exc:  # noqa: BLE001 — retain other detail rows
                return teaser, None, exc

        parsed = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            for teaser, html, error in executor.map(fetch_detail, teasers):
                if error:
                    print(f"  Related Rentals detail {teaser['api_id']} failed: {error}")
                    continue
                preliminary = self._parse_detail(html, teaser["url"], teaser, retrieved_at)
                if preliminary:
                    parsed.append((teaser, html, preliminary["address"]))

        addresses = sorted({address for _, _, address in parsed})
        with ThreadPoolExecutor(max_workers=4) as executor:
            crosswalks = dict(zip(
                addresses,
                executor.map(lambda address: _dob_crosswalk(address, retrieved_at), addresses),
            ))

        listings = []
        for teaser, html, address in parsed:
            bbl, bbl_evidence = crosswalks[address]
            row = self._parse_detail(html, teaser["url"], teaser, retrieved_at, bbl, bbl_evidence)
            if row:
                listings.append(row)
        print(f"  checked {len(teasers)} NYC availability cards")
        print(f"  {len(listings)} explicit unit-detail rows")
        return listings
