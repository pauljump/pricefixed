"""Corcoran — current NYC rental listings from the public backend API.

Corcoran (like Douglas Elliman and Compass) is a brokerage, not a landlord. Its search
returns its own exclusives AND, through IDX/MLS syndication (`isIdx` / `isMLS` on nearly
every row), listings from across the REBNY RLS feed. So a single brokerage source reaches
far more of the real NYC broker market than any one landlord-direct feed — the syndicated
feed rides along for free.

We pull ONLY *active, on-market* listings: `transactionTypes:["for-rent"]` with no status
filter. The same backend can also serve closed sold/rented *history* (via `listingStatus`),
and that historical-rent layer is deliberately NOT touched here. Current public asking rents
are fair game — the same category as a landlord publishing its own vacancies; the closed-rent
history is the part the walled resellers charge for, and it stays off this open tool. A
defensive `_is_active` filter below also drops anything that isn't currently active, so no
closed row can leak into the open dataset even if the API's defaults ever change.

Endpoint: POST backendapi.corcoranlabs.com/api/search/listings. The `be-api-key` is
Corcoran's own public web-app key — the same value their site sends from every visitor's
browser, not a credential of ours. Override with the CORCORAN_API_KEY env var if it rotates
(the healthcheck turns red when it does, which is the signal to update it).

No third-party dependencies. Python 3.9+ standard library only.
"""
from __future__ import annotations

import json
import os
import time

from ..core import SourceAdapter, fetch

API_URL = "https://backendapi.corcoranlabs.com/api/search/listings"
# Corcoran's public front-end API key (embedded in their own web app, sent by every
# browser that loads corcoran.com). Not a secret; override via env if they rotate it.
DEFAULT_API_KEY = "667256B5BF6ABFF6C8BDC68E88226"
REGION_NYC = "1"
PAGE_SIZE = 100          # the API's max page size
MAX_PAGES = 400          # safety rail; active NYC rentals is ~2k (~20 pages)
DELAY = 0.2              # a beat between pages — gentle by default


def _api_key():
    return os.environ.get("CORCORAN_API_KEY", DEFAULT_API_KEY)


def _search_page(page):
    """One page of the active for-rent search. NEVER sends a listingStatus/closed filter."""
    body = json.dumps({
        "page": page,
        "pageSize": PAGE_SIZE,
        "regionIds": [REGION_NYC],
        "transactionTypes": ["for-rent"],   # active on-market rentals only
        "sortBy": ["price+asc"],
    }).encode()
    headers = {
        "be-api-key": _api_key(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    return json.loads(fetch(API_URL, headers=headers, data=body, method="POST"))


def _is_active(item):
    """Moat guard: keep only currently-advertised listings. The query already asks for
    active for-rent, but we re-check status and reject anything with a closed-rented date
    so no historical (sold/rented) row can ever slip into the open dataset."""
    status = (item.get("listingStatus") or "").strip().lower()
    return status in ("", "active") and not item.get("closedRentedDate")


def _to_listing(item):
    loc = item.get("location") or {}
    media = item.get("mediaUrl")
    price = item.get("price")
    attribution = item.get("listingAttribution") or item.get("listingAgency")
    return {
        "source_id": str(item.get("listingId", "")),
        "building_name": item.get("buildingName"),
        "address": item.get("address1"),
        "unit_number": item.get("address2") or item.get("unitType"),
        "bedrooms": item.get("bedrooms"),
        "bathrooms": item.get("totalBathrooms") or item.get("bathrooms"),
        "price": price,
        "sqft": item.get("squareFootage") or item.get("squareFeetInterior"),
        "available_date": item.get("availableDate") or item.get("dateAvailable"),
        "lease_terms": json.dumps([{"term": "annual", "price": price}]) if price else None,
        "description": f"Listed by {attribution}" if attribution else None,
        "image_urls": json.dumps([media]) if media else None,
        "latitude": loc.get("latitude"),
        "longitude": loc.get("longitude"),
        "neighborhood": item.get("neighborhoodName"),
        "borough": item.get("boroughName"),
        "zipcode": item.get("zipCode"),
        "raw_json": json.dumps(item),
    }


class CorcoranSource(SourceAdapter):
    name = "corcoran"
    description = ("Corcoran — current NYC rental listings via the public backend API "
                  "(active for-rent, incl. IDX/MLS-syndicated broker listings)")

    def pull(self):
        first = _search_page(1)
        total_pages = min(int(first.get("totalPages") or 0), MAX_PAGES)
        print(f"  {first.get('totalItems', 0):,} active for-rent listings, "
              f"{first.get('totalPages', 0)} pages (pulling up to {total_pages})")

        items = list(first.get("items") or [])
        for page in range(2, total_pages + 1):
            time.sleep(DELAY)
            data = _search_page(page)
            page_items = data.get("items") or []
            if not page_items:
                break
            items.extend(page_items)

        # Map + moat guard: only currently-active rows, and only rows with a real id.
        return [_to_listing(it) for it in items
                if it.get("listingId") and _is_active(it)]
