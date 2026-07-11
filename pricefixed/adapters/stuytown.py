"""Beam Living — StuyTown, Peter Cooper Village, Kips Bay Court, Parker Towers, 8 Spruce.
Public JSON availability API (the same one their own site calls). Includes per-lease-term
pricing, which is where algorithmic lease-length steering shows up."""
import json

from ..core import SourceAdapter, fetch

API_URL = "https://units.stuytown.com/api/units?itemsOnPage=500&Order=low-price"

# property name -> (neighborhood, borough). Note: "Parker Towers" is Forest Hills, QUEENS,
# not Manhattan — a good reminder that a landlord's own labels are not geography.
PROPERTY_HOODS = {
    "Stuyvesant Town": ("Stuyvesant Town", "Manhattan"),
    "Peter Cooper Village": ("Peter Cooper Village", "Manhattan"),
    "Kips Bay Court": ("Kips Bay", "Manhattan"),
    "Parker Towers": ("Forest Hills", "Queens"),
    "8 Spruce": ("Financial District", "Manhattan"),
}


class StuyTownAdapter(SourceAdapter):
    name = "stuytown"
    description = "Beam Living (StuyTown / PCV / Kips Bay / Parker Towers / 8 Spruce)"

    def pull(self):
        data = json.loads(fetch(API_URL))
        units = data.get("unitModels", [])
        print(f"  API returned {len(units)} units")
        out = []
        for u in units:
            if not u.get("isAvailable"):
                continue
            bldg = u.get("building", {}) or {}
            prop = u.get("property", {}) or {}
            hood, boro = PROPERTY_HOODS.get(prop.get("name", ""), ("", ""))
            rates = u.get("unitRates") or {}
            lease_terms = json.dumps(
                [{"term": f"{k} months", "price": v} for k, v in sorted(rates.items(), key=lambda x: int(x[0]))]
            ) if rates else None
            out.append({
                "source_id": u.get("unitSpk", ""),
                "building_name": f"{prop.get('name', '')} — {bldg.get('name', '')}".strip(" —"),
                "address": bldg.get("address", ""),
                "unit_number": u.get("unitNumber", ""),
                "bedrooms": u.get("bedrooms", 0),
                "bathrooms": u.get("bathrooms"),
                "price": u.get("price"),
                "sqft": u.get("sqft"),
                "available_date": (u.get("availableDate") or "")[:10] or None,
                "lease_terms": lease_terms,
                "neighborhood": hood,
                "borough": boro,
                "is_flex": 1 if u.get("isFlex") else 0,
                "is_rent_stabilized": 1 if u.get("isCapped") else 0,
                "finish_level": (u.get("finish") or {}).get("name"),
                "raw_json": json.dumps(u, default=str),
            })
        return out
