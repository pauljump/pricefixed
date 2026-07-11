"""Nooklyn — broker marketplace. This is the no-fee / small-landlord inventory that the
big-landlord feeds never contain. Paginated JSON. Prices are in CENTS (435000 = $4,350)."""
import json
import re
import time

from ..core import SourceAdapter, fetch

API_URL = "https://nooklyn.com/api/v2/listings.search"
CITY_TO_BORO = {
    "Manhattan": "Manhattan", "Brooklyn": "Brooklyn", "Queens": "Queens", "Bronx": "Bronx",
    "Staten Island": "Staten Island", "Astoria": "Queens", "Long Island City": "Queens",
    "Jamaica": "Queens", "Flushing": "Queens", "Ridgewood": "Queens", "Woodside": "Queens",
    "Jackson Heights": "Queens", "Sunnyside": "Queens", "Corona": "Queens", "Elmhurst": "Queens",
    "Forest Hills": "Queens", "Riverdale": "Bronx", "Mott Haven": "Bronx", "Fordham": "Bronx",
}


class NooklynAdapter(SourceAdapter):
    name = "nooklyn"
    description = "Nooklyn — broker marketplace (no-fee / small-landlord inventory)"

    def _page(self, page):
        body = json.dumps({"page": page, "per_page": 100, "type": "residential", "transaction": "rentals"}).encode()
        return json.loads(fetch(API_URL, headers={"Content-Type": "application/json"}, data=body))

    def pull(self):
        first = self._page(1)
        pages = first.get("page_count", 1)
        print(f"  {first.get('total_count', 0)} total listings, {pages} pages")
        rows = list(first.get("listings", []))
        for p in range(2, pages + 1):
            try:
                rows.extend(self._page(p).get("listings", []))
            except Exception as e:  # noqa: BLE001
                print(f"  page {p}: {e}")
            time.sleep(0.4)
        out = []
        for L in rows:
            try:
                out.append(self._map(L))
            except Exception:  # noqa: BLE001 — skip a malformed row, keep the pull
                pass
        return [x for x in out if x]

    def _map(self, L):
        price = L.get("price")
        price = price / 100.0 if price is not None else None  # cents -> dollars
        addr_full = L.get("address", "") or ""
        street, city, zipcode = addr_full, "", None
        m = re.search(r"^(.*?),\s*(.*?),\s*([A-Z]{2})\s+(\d{5})", addr_full)
        if m:
            street, city, zipcode = m.group(1).strip(), m.group(2).strip(), m.group(4)
        unit_m = re.search(r"Unit:\s*(.+)$", L.get("short_address") or "", re.I)
        hood = L.get("neighborhood")
        hood = hood.get("name") if isinstance(hood, dict) else (hood if isinstance(hood, str) else None)
        avail = L.get("date_available")
        return {
            "source_id": str(L.get("id", "")),
            "address": street,
            "unit_number": unit_m.group(1).strip() if unit_m else None,
            "bedrooms": L.get("bedrooms"),
            "bathrooms": L.get("bathrooms"),
            "price": price,
            "sqft": L.get("square_feet"),
            "available_date": avail[:10] if avail and len(avail) >= 10 else None,
            "description": L.get("description"),
            "latitude": L.get("latitude"),
            "longitude": L.get("longitude"),
            "neighborhood": hood,
            "borough": CITY_TO_BORO.get(city, "Manhattan" if city == "New York" else city or None),
            "zipcode": zipcode,
            "raw_json": json.dumps(L, default=str),
        }
