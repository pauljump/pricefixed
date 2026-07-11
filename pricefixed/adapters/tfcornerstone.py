"""TF Cornerstone — Manhattan / Brooklyn / Queens portfolio (~20 buildings).
One static JSON feed powers their whole site. Cleanest possible target."""
import json

from ..core import SourceAdapter, fetch

API_URL = "https://cdn.tfc.com/tfc-com/initial-data.json"
CITY_TO_BORO = {
    "New York": "Manhattan", "Brooklyn": "Brooklyn", "Astoria": "Queens",
    "Long Island City": "Queens", "Queens": "Queens", "Bronx": "Bronx",
    "Staten Island": "Staten Island",
}


class TFCornerstoneAdapter(SourceAdapter):
    name = "tfcornerstone"
    description = "TF Cornerstone — luxury portfolio (~20 buildings)"

    def pull(self):
        data = json.loads(fetch(API_URL, timeout=60))
        units = (data.get("Units") or {}).get("Data", []) or []
        props = (data.get("Properties") or {}).get("Data", []) or []
        prop_by_code = {p["Code"]: p for p in props}
        print(f"  {len(units)} listed units, {len(props)} properties")
        out = []
        for u in units:
            if not u.get("IsListed"):
                continue
            prop = prop_by_code.get(u.get("PropertyCode", ""), {})
            images = u.get("Images") or []
            out.append({
                "source_id": u.get("Code", ""),
                "building_name": prop.get("Name", ""),
                "address": prop.get("Address", u.get("Address", "")),
                "unit_number": str(u.get("Apartment", "")),
                "bedrooms": u.get("NumBedrooms", 0),
                "bathrooms": u.get("NumBathrooms"),
                "price": u.get("Price"),
                "available_date": (u.get("Availability") or "")[:10] or None,
                "amenities": json.dumps(u.get("UnitFeatureCodes")) if u.get("UnitFeatureCodes") else None,
                "description": u.get("Description"),
                "floor_plan_url": u.get("Floorplan") or u.get("FloorplanPrint"),
                "image_urls": json.dumps([
                    img if isinstance(img, str) else (img.get("FullUrl", "") if isinstance(img, dict) else str(img))
                    for img in images
                ]) if images else None,
                "latitude": float(prop["Latitude"]) if prop.get("Latitude") else None,
                "longitude": float(prop["Longitude"]) if prop.get("Longitude") else None,
                "neighborhood": u.get("Neighborhood") or prop.get("NeighborhoodCode", ""),
                "borough": CITY_TO_BORO.get(prop.get("City", "New York"), "Manhattan"),
                "zipcode": prop.get("Zip"),
                "raw_json": json.dumps(u, default=str),
            })
        return out
