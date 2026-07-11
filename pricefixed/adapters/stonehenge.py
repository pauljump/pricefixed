"""Stonehenge Management — 20 luxury NYC buildings behind a Salesforce apexrest endpoint.
Two calls: list buildings, then list units per building. Unit metadata (bed/bath/apt/price)
is packed into one human-readable `label` string that we parse out with regex."""
import json
import re
import time

from ..core import SourceAdapter, fetch


class StonehengeAdapter(SourceAdapter):
    name = "stonehenge"
    description = "Stonehenge Management — Salesforce API (20 luxury NYC buildings)"

    API_URL = "https://stonehenge.my.site.com/services/apexrest/webflow/apply-now/"

    def pull(self):
        # Step 1: Get all buildings
        raw = fetch(self.API_URL, headers={"Accept": "application/json"})
        buildings = json.loads(raw)
        print(f"  {len(buildings)} buildings")

        all_units = []
        for bldg in buildings:
            code = bldg.get("value", "")
            label = bldg.get("label", "")
            try:
                units_raw = fetch(
                    f"{self.API_URL}?buildingCode={code}",
                    headers={"Accept": "application/json"}
                )
                units = json.loads(units_raw)
            except Exception:  # noqa: BLE001
                continue

            for u in units:
                # Parse: "1 Bedroom | Bath 1.0 | Apt 015M | $4945"
                info = u.get("label", "")
                beds = 0
                baths = 1
                unit_num = ""
                price = None

                bed_m = re.search(r'(\d+)\s*Bedroom', info, re.I)
                if bed_m:
                    beds = int(bed_m.group(1))
                elif 'Studio' in info:
                    beds = 0

                bath_m = re.search(r'Bath\s*([\d.]+)', info, re.I)
                if bath_m:
                    baths = float(bath_m.group(1))

                apt_m = re.search(r'Apt\s*(\S+)', info, re.I)
                if apt_m:
                    unit_num = apt_m.group(1)

                price_m = re.search(r'\$([\d,]+)', info)
                if price_m:
                    price = int(price_m.group(1).replace(",", ""))

                all_units.append({
                    "source_id": f"stonehenge-{u.get('value', '')}",
                    "building_name": label,
                    "address": "",
                    "unit_number": unit_num,
                    "bedrooms": beds,
                    "bathrooms": baths,
                    "price": price,
                    "sqft": None,
                    "available_date": None,
                    "lease_terms": None,
                    "amenities": None,
                    "description": None,
                    "floor_plan_url": None,
                    "image_urls": None,
                    "latitude": None,
                    "longitude": None,
                    "neighborhood": "",
                    "borough": "Manhattan",
                    "zipcode": None,
                    "is_flex": 0,
                    "is_rent_stabilized": 0,
                    "finish_level": None,
                    "raw_json": json.dumps(u),
                })

            if units:
                print(f"    {label}: {len(units)} units")
            time.sleep(0.3)

        return all_units
