"""Douglas Elliman — current NYC rental listings via the MLS-backed core API.

Elliman's core API (`core.api.elliman.com`) is backed by the Trestle/CoreLogic MLS feed,
so — like Corcoran — its search returns far beyond Elliman's own exclusives: it's the
broker market riding the RLS/MLS syndication. One adapter, a large slice of the whole
listed market, no feed license. (See `corcoran.py` and FEEDS.md for the shared method.)

Same open/private line: we request ONLY `statuses:["Active"]` + `listingTypes:["ResidentialLease"]`
— current on-market rentals. The same endpoint will serve the `Closed` sold/rented *history*
(with `closePrice`/`closeDate`), and that historical-rent layer is deliberately NOT touched.
A defensive `_is_active` filter also drops anything carrying a close date/price, so no closed
row can leak into the open dataset even if the API's defaults change.

Auth needs no key or login: the API accepts a header derived from the current timestamp
(base64 of the millisecond epoch, each char shifted down 10). Nothing secret, nothing ours.

The API recycles results after ~300 per query, so to reach more than a slice we partition
each borough by bedroom count and paginate every bucket until it stops returning new ids.

No third-party dependencies. Python 3.9+ standard library only.
"""
from __future__ import annotations

import base64
import json
import re
import time

from ..core import SourceAdapter, fetch

# NYC zips often sit only in the address string, not the postalCode field — recover them.
_ZIP = re.compile(r"(\d{5})(?:-\d{4})?\s*$")

API_URL = "https://core.api.elliman.com/listing/filter"
PAGE = 100
MAX_SKIP = 4999        # the API's hard skip ceiling
RESULT_CAP = 300       # it recycles ids past ~300 per query — the signal to sub-partition
DELAY = 0.15           # a beat between requests — gentle by default

# Borough "place" objects the filter expects (ids from Elliman's own place index).
BOROUGHS = [
    {"id": 1915, "urlKey": "manhattan-ny", "name": "Manhattan"},
    {"id": 1908, "urlKey": "brooklyn-ny", "name": "Brooklyn"},
    {"id": 1925, "urlKey": "queens-ny", "name": "Queens"},
    {"id": 337218, "urlKey": "bronx--county-ny", "name": "Bronx"},
    {"id": 1927, "urlKey": "staten-island-ny", "name": "Staten Island"},
]
BEDROOMS = [0, 1, 2, 3, 4, 5]   # 5 = 5+, used only when a borough hits the cap


def _headers():
    """The timestamp-derived header the core API expects. No key, no login, no secret."""
    ts = str(int(time.time() * 1000))
    b64 = base64.b64encode(ts.encode()).decode()
    shifted = "".join(chr(ord(c) - 10) for c in b64)
    return {
        "Cookies": "static/" + shifted,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _filter(place, bedrooms=None, skip=0):
    """Build the search filter. statuses is ALWAYS ["Active"] — never a closed status."""
    return {
        "styles": None, "statuses": ["Active"], "features": None, "homeTypes": None,
        "timeOnMls": None, "isAgencyOnly": False, "isPetAllowed": False,
        "hasOpenHouse": False, "rentalPeriods": None,
        "bedroomsTotal": [bedrooms] if bedrooms is not None else None,
        "isPriceReduced": False, "hasVirtualTour": False, "isNewConstruction": False,
        "onlyInternationalListings": False, "listingTypes": ["ResidentialLease"],
        "checkedStatuses": [],
        "bathroom": {"queryField": "TotalDecimal", "operator": "Ge", "value": None},
        "listPrice": {"min": None, "max": None},
        "yearBuilt": {"min": None, "max": None},
        "lotSizeSquareFeet": {"min": None, "max": None},
        "livingAreaSquareFeet": {"min": None, "max": None},
        "orderBy": "Newest",
        "parkingTotal": {"min": None, "max": None},
        "schoolFilter": {"score": None, "isPrivate": None},
        "moveIn": {"date": None, "skipNulls": None},
        "skip": skip, "take": PAGE,
        "places": [{"id": place["id"], "urlKey": place["urlKey"],
                    "name": place["name"], "shapeId": None}],
    }


def _post(filt):
    body = json.dumps({"filter": filt, "map": {"zoomLevel": 11, "geometry": None}}).encode()
    return json.loads(fetch(API_URL, headers=_headers(), data=body, method="POST"))


def _paginate(place, bedrooms=None):
    """Page one query bucket until the API stops returning new ids (it recycles past ~300).
    Returns {coreListingId: raw_item}."""
    seen = {}
    for skip in range(0, MAX_SKIP + 1, PAGE):
        data = _post(_filter(place, bedrooms, skip))
        items = data.get("listings") or []
        if not items:
            break
        new = 0
        for it in items:
            cid = it.get("coreListingId")
            if cid and cid not in seen:
                seen[cid] = it
                new += 1
        if new == 0:      # ids recycling — this bucket is exhausted
            break
        time.sleep(DELAY)
    return seen


def _is_active(it):
    """Moat guard: keep only current on-market rows. The query asks Active only, but we
    re-check and reject anything carrying a close date/price so no closed (sold/rented)
    row from the same MLS can ever slip into the open dataset."""
    status = (it.get("listingStatus") or "").strip().lower()
    return status == "active" and not it.get("closeDate") and not it.get("closePrice")


def _to_listing(it, borough):
    addr = it.get("address") or {}
    latlng = it.get("latLng") or {}
    price = it.get("listPrice")
    full = addr.get("samlsFullAddress") or addr.get("samlsPartialAddress")
    zipcode = addr.get("postalCode")
    if not zipcode and full:
        m = _ZIP.search(full.strip())
        if m:
            zipcode = m.group(1)
    images = [i.get("url") for i in (it.get("images") or []) if i.get("url")][:10]
    return {
        "source_id": str(it.get("coreListingId", "")),
        "building_name": it.get("buildingName"),
        "address": full,
        "unit_number": addr.get("unitNumber"),
        "bedrooms": it.get("bedroomsTotal"),
        "bathrooms": it.get("bathroomsTotal"),
        "price": price,
        "sqft": it.get("livingAreaSquareFeet"),
        "lease_terms": json.dumps([{"term": "annual", "price": price}]) if price else None,
        "description": it.get("brokerAttribution"),
        "image_urls": json.dumps(images) if images else None,
        "latitude": latlng.get("lat"),
        "longitude": latlng.get("lng"),
        "neighborhood": addr.get("neighborhood"),
        "borough": borough,
        "zipcode": zipcode,
        "raw_json": json.dumps(it),
    }


class EllimanSource(SourceAdapter):
    name = "elliman"
    description = ("Douglas Elliman — current NYC rental listings via the MLS-backed core API "
                  "(active leases, incl. RLS-syndicated broker listings)")

    def pull(self):
        by_id = {}          # coreListingId -> (raw_item, borough)
        for boro in BOROUGHS:
            got = _paginate(boro)
            # If the borough saturated the cap, split it by bedroom to reach under it.
            if len(got) >= RESULT_CAP:
                for beds in BEDROOMS:
                    for cid, it in _paginate(boro, beds).items():
                        got.setdefault(cid, it)
            for cid, it in got.items():
                by_id.setdefault(cid, (it, boro["name"]))
            print(f"  {boro['name']}: {len(got)} active rentals")

        return [_to_listing(it, boro) for (it, boro) in by_id.values()
                if it.get("coreListingId") and _is_active(it)]
