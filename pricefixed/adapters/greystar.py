"""Greystar's public NYC property search and property JSON endpoints.

The public Greystar site searches a Coveo index, then exposes each property's
current ``availableUnits`` through ``/api/property/<id>``.  This adapter keeps
only explicit unit rows for the five boroughs.  A floorplan without an
``availableUnits`` row is deliberately not expanded into a unit.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from ..core import SourceAdapter, fetch


class GreystarAdapter(SourceAdapter):
    name = "greystar"
    description = "Greystar public property JSON — NYC five boroughs only"

    SEARCH_URL = (
        "https://platform.cloud.coveo.com/rest/organizations/"
        "greystarproduction117hu38yh/commerce/v2/search"
        "?trackingId=greystar_com_tracking_id"
    )
    PROPERTY_URL = "https://www.greystar.com/api/property/{}"
    SEARCH_QUERY = '@greystar_market_area=="New York City"'
    # This is the public client token embedded in Greystar's website JavaScript.
    # It is not an account credential; override it if the public site rotates it.
    COVEO_TOKEN = "xxc151470d-e78b-4285-95bb-a62d0aa027da"
    NYC_CITIES = {"New York", "Brooklyn", "Queens", "Bronx", "Staten Island"}

    def _search(self):
        payload = json.dumps({
            "clientId": "greystarproduction117hu38yh",
            "context": {"view": {"url": "https://www.greystar.com"}, "capture": False},
            "country": "US",
            "currency": "USD",
            "language": "en",
            "query": self.SEARCH_QUERY,
            "trackingId": "greystar_com_tracking_id",
        }).encode()
        raw = fetch(
            self.SEARCH_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.COVEO_TOKEN}",
            },
            data=payload,
            method="POST",
            timeout=45,
        )
        return json.loads(raw)

    @staticmethod
    def _property_id(product):
        click_uri = str(product.get("clickUri") or "")
        prefix = "property://"
        if not click_uri.startswith(prefix):
            return None
        value = click_uri[len(prefix):].strip("/")
        return value if value.isdigit() else None

    @classmethod
    def _parse_property(cls, property_data, search_url, retrieved_at):
        location = property_data.get("location") or {}
        city = str(location.get("city") or "").strip()
        if city not in cls.NYC_CITIES:
            return []
        address = str(location.get("address") or "").strip()
        if not address:
            return []
        floorplans = {
            str(plan.get("id")): plan
            for plan in property_data.get("floorplans") or []
            if plan.get("id") is not None
        }
        source_url = cls.PROPERTY_URL.format(property_data.get("id"))
        rows = []
        for unit in property_data.get("availableUnits") or []:
            unit_number = str(unit.get("unitNumber") or "").strip()
            unit_id = str(unit.get("unitId") or "").strip()
            if not unit_number or not unit_id:
                continue
            plan = floorplans.get(str(unit.get("floorPlanId"))) or {}
            raw = {
                "source": "greystar",
                "source_url": source_url,
                "search_url": search_url,
                "retrieved_at": retrieved_at,
                "property": property_data,
                "available_unit": unit,
            }
            rows.append({
                "source_id": f"gs-{property_data.get('id')}-{unit_id}",
                "building_name": property_data.get("name"),
                "address": address,
                "unit_number": unit_number,
                "bedrooms": plan.get("bedroomCount"),
                "bathrooms": plan.get("bathroomCount"),
                "price": unit.get("minPrice"),
                "sqft": unit.get("area"),
                "available_date": unit.get("availableOn"),
                "lease_terms": unit.get("minBaseRentLeaseTerm"),
                "amenities": None,
                "description": None,
                "floor_plan_url": plan.get("imageUrl"),
                "image_urls": None,
                "latitude": location.get("latitude"),
                "longitude": location.get("longitude"),
                "neighborhood": location.get("greystarNeighborhood"),
                "borough": city,
                "zipcode": location.get("postalCode"),
                "is_flex": 0,
                "is_rent_stabilized": 0,
                "finish_level": None,
                "raw_json": json.dumps(raw, default=str, sort_keys=True),
            })
        return rows

    def pull(self):
        retrieved_at = datetime.now(timezone.utc).isoformat()
        try:
            search = self._search()
        except Exception as exc:  # noqa: BLE001
            print(f"  Greystar search failed: {exc}")
            return []
        search_url = self.SEARCH_URL
        products = search.get("products") or []
        listings = []
        property_count = 0
        for product in products:
            property_id = self._property_id(product)
            if not property_id:
                continue
            try:
                raw = fetch(self.PROPERTY_URL.format(property_id), timeout=45)
                property_data = json.loads(raw)
            except Exception as exc:  # noqa: BLE001
                print(f"  Greystar property {property_id} failed: {exc}")
                continue
            property_count += 1
            listings.extend(self._parse_property(property_data, search_url, retrieved_at))
        print(f"  checked {property_count} public NYC property records")
        print(f"  {len(listings)} explicit available-unit rows")
        return listings
