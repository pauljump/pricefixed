"""Dermot Company — public Nestio availability for confirmed New York properties.

Dermot's official building pages call the public ``nestiolistings.com`` API and
expose a community id in the page markup. The API returns current vacancies with
the manager's unit label and exact street address. This is listing evidence only:
it is not a complete apartment roster and must never be expanded from building
counts or the page's floorplan tables.
"""
import json
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

from ..core import SourceAdapter, fetch


API_BASE = "https://nestiolistings.com/api/v2/listings/all"
# This is the public New York web-app key embedded in Dermot's official page.
PUBLIC_API_KEY = "7536d35593414ef29a6696a9dc35b6fc"


# Confirmed by fetching the official page and then the page-linked public API.
# Florida properties and pages without a confirmed NY community response are
# intentionally excluded.
PROPERTIES = [
    {"community_id": 3151, "url": "https://www.dermotcompany.com/building/101-west-end-avenue"},
    {"community_id": 5740, "url": "https://www.dermotcompany.com/building/20-exchange"},
    {"community_id": 3388, "url": "https://www.dermotcompany.com/building/21-west-end-ave"},
    {"community_id": 3152, "url": "https://www.dermotcompany.com/building/220-east-72nd-street"},
    {"community_id": 3226, "url": "https://www.dermotcompany.com/building/535-w-43rd-street"},
    {"community_id": 3150, "url": "https://www.dermotcompany.com/building/66-rockwell-place"},
    {"community_id": 3756, "url": "https://www.dermotcompany.com/building/alta"},
    {"community_id": 3321, "url": "https://www.dermotcompany.com/building/moda"},
    {"community_id": 3387, "url": "https://www.dermotcompany.com/building/the-addison"},
    {"community_id": 3836, "url": "https://www.dermotcompany.com/building/the-bergen"},
    {"community_id": 3274, "url": "https://www.dermotcompany.com/building/the-buchanan"},
    {"community_id": 5672, "url": "https://www.dermotcompany.com/building/the-chrystie"},
    {"community_id": 3320, "url": "https://www.dermotcompany.com/building/the-colorado"},
    {"community_id": 3275, "url": "https://www.dermotcompany.com/building/the-kestrel"},
    {"community_id": 3923, "url": "https://www.dermotcompany.com/building/the-landing"},
    {"community_id": 3269, "url": "https://www.dermotcompany.com/building/the-landon"},
    {"community_id": 3386, "url": "https://www.dermotcompany.com/building/the-vitagraph"},
]


def _api_url(community_id, page=None):
    params = {"key": PUBLIC_API_KEY, "property": community_id}
    if page is not None:
        params["page"] = page
    return f"{API_BASE}?{urlencode(params)}"


def _date(value):
    value = str(value or "").strip()
    return value[:10] if value else None


def _map_listing(item, prop, retrieved_at):
    """Map one API item, rejecting anything that cannot be exact-address evidence."""
    building = item.get("building") or {}
    community = building.get("community") or {}
    address = str(building.get("street_address") or community.get("street_address") or "").strip()
    unit_number = str(item.get("unit_number") or "").strip()
    source_item_id = item.get("id")
    state = str(building.get("state") or community.get("state") or "").upper()
    if state != "NY" or not address or not unit_number or source_item_id is None:
        return None

    raw = dict(item)
    raw["_pricefixed_source_url"] = prop["url"]
    raw["_pricefixed_feed_url"] = _api_url(prop["community_id"])
    raw["_pricefixed_retrieved_at"] = retrieved_at
    return {
        "source_id": f"dermot-{prop['community_id']}-{source_item_id}",
        "building_name": str(building.get("name") or item.get("name") or "").strip(),
        "address": address,
        "unit_number": unit_number,
        "bedrooms": item.get("bedrooms"),
        "bathrooms": item.get("bathrooms"),
        "price": float(item["price"]) if item.get("price") not in (None, "") else None,
        "sqft": item.get("square_footage"),
        "available_date": _date(item.get("date_available")),
        "lease_terms": None,
        "amenities": json.dumps(building.get("amenities")) if building.get("amenities") else None,
        "description": building.get("building_description"),
        "floor_plan_url": None,
        "image_urls": None,
        "latitude": (item.get("location") or {}).get("latitude"),
        "longitude": (item.get("location") or {}).get("longitude"),
        "neighborhood": (item.get("neighborhood") or {}).get("name"),
        "borough": building.get("city"),
        "zipcode": building.get("postal_code") or community.get("postal_code"),
        "is_flex": 0,
        "is_rent_stabilized": 0,
        "finish_level": None,
        "raw_json": json.dumps(raw, default=str),
    }


class DermotAdapter(SourceAdapter):
    name = "dermot"
    description = "Dermot Company — public Nestio availability for 17 confirmed NY properties"
    PROPERTIES = PROPERTIES

    def _fetch_property(self, prop):
        first_url = _api_url(prop["community_id"])
        data = json.loads(fetch(first_url))
        items = list(data.get("items") or [])
        total_pages = int(data.get("total_pages") or 1)
        for page in range(2, total_pages + 1):
            page_data = json.loads(fetch(_api_url(prop["community_id"], page=page)))
            items.extend(page_data.get("items") or [])
        retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        return [mapped for item in items if (mapped := _map_listing(item, prop, retrieved_at))]

    def pull(self):
        all_units = []
        for prop in self.PROPERTIES:
            try:
                units = self._fetch_property(prop)
                print(f"  community {prop['community_id']}: {len(units)} listings")
                all_units.extend(units)
            except Exception as exc:  # noqa: BLE001 — one property must not hide the rest
                print(f"  community {prop['community_id']}: ERROR — {exc}")
            time.sleep(0.25)
        return all_units
