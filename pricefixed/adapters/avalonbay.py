"""AvalonBay Communities — proprietary units API (apis.avalonbay.com/search/units).
A single JSON call over a NYC bounding box + move-in window returns every available unit;
we keep NY-state rows. Per-unit furnished/unfurnished pricing is preserved in raw_json."""
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from ..core import SourceAdapter, fetch


class AvalonBayAdapter(SourceAdapter):
    name = "avalonbay"
    description = "AvalonBay Communities — proprietary API (NYC metro, NY units only)"

    API_URL = "https://apis.avalonbay.com/search/units"
    API_KEY = "dBC7Zs9At52EMirrcwn48ayie0H3JLWX9QGi22jM"

    # NYC bounding box: top-left (NW) to bottom-right (SE)
    TOP_LEFT     = "40.9176,-74.2591"
    BOTTOM_RIGHT = "40.4774,-73.7004"

    # city → borough for NY addresses
    CITY_TO_BORO = {
        "New York": "Manhattan",
        "Brooklyn": "Brooklyn",
        "Bronx": "Bronx",
        "Staten Island": "Staten Island",
        "Astoria": "Queens",
        "Long Island City": "Queens",
        "Jamaica": "Queens",
        "Flushing": "Queens",
    }

    def pull(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        max_date = (datetime.now(timezone.utc) + timedelta(days=180)).strftime("%Y-%m-%d")

        params = urlencode({
            "topLeftCoords": self.TOP_LEFT,
            "bottomRightCoords": self.BOTTOM_RIGHT,
            "minMoveInDate": today,
            "maxMoveInDate": max_date,
        })
        url = f"{self.API_URL}?{params}"

        try:
            raw = fetch(url, headers={"x-api-key": self.API_KEY}, timeout=45)
        except Exception as e:  # noqa: BLE001
            print(f"  AvalonBay fetch failed: {e}")
            return []

        try:
            data = json.loads(raw)
        except Exception as e:  # noqa: BLE001
            print(f"  AvalonBay JSON parse failed: {e}")
            return []

        items = data.get("items", [])
        print(f"  {data.get('itemsCount', len(items))} total items from API")

        listings = []
        for u in items:
            addr = u.get("address", {}) or {}
            state = addr.get("state", "")
            if state != "NY":
                continue

            # Price: prefer unfurnished; fall back to furnished
            price = None
            for price_key in ("startingAtPricesUnfurnished", "startingAtPricesFurnished"):
                pdata = u.get(price_key) or {}
                prices = pdata.get("prices", {}) or {}
                if prices.get("price") is not None:
                    price = float(prices["price"])
                    break

            # Available date
            avail_raw = u.get("availableDateUnfurnished") or u.get("availableDateFurnished")
            avail_date = avail_raw[:10] if avail_raw else None

            # Floor plan
            fp = u.get("floorPlan") or {}
            fp_url = fp.get("highResolution")
            if fp_url and not fp_url.startswith("http"):
                fp_url = "https://www.avalonbay.com" + fp_url

            city = addr.get("city", "")
            boro = self.CITY_TO_BORO.get(city, city or None)

            # Unit name often includes unit number e.g. "19N"
            unit_name = u.get("unitName", "")
            # community name sometimes includes unit: "200 Boyden Ave #264"
            addr_line = addr.get("addressLine1", "")
            # Extract unit from addressLine1 if present
            unit_from_addr = None
            um = re.search(r"#(.+)$", addr_line)
            if um:
                unit_from_addr = um.group(1).strip()
                addr_line = addr_line[:um.start()].strip()

            listings.append({
                "source_id": u.get("unitId", ""),
                "building_name": u.get("communityName", ""),
                "address": addr_line or addr.get("addressLine1", ""),
                "unit_number": unit_from_addr or unit_name or None,
                "bedrooms": u.get("bedroomNumber"),
                "bathrooms": u.get("bathroomNumber"),
                "price": price,
                "sqft": u.get("squareFeet"),
                "available_date": avail_date,
                "lease_terms": None,
                "amenities": None,
                "description": None,
                "floor_plan_url": fp_url,
                "image_urls": None,
                "latitude": None,
                "longitude": None,
                "neighborhood": None,
                "borough": boro,
                "zipcode": addr.get("zip"),
                "is_flex": 0,
                "is_rent_stabilized": 0,
                "finish_level": u.get("furnishStatus"),
                "raw_json": json.dumps(u, default=str),
            })

        ny_count = len(listings)
        print(f"  {ny_count} NY listings")
        return listings
