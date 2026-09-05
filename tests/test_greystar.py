import json
import unittest

from pricefixed.adapters.greystar import GreystarAdapter


class GreystarAdapterTest(unittest.TestCase):
    def test_keeps_explicit_available_units_and_not_floorplans(self):
        property_data = {
            "id": "21037",
            "name": "345 E 94",
            "location": {
                "address": "345 East 94th St",
                "city": "New York",
                "postalCode": "10128",
                "latitude": 40.78,
                "longitude": -73.94,
                "greystarNeighborhood": "Upper East Side",
            },
            "floorplans": [
                {"id": "p1", "bedroomCount": 1, "bathroomCount": 1,
                 "imageUrl": "https://example.test/p1.png"},
                {"id": "p2", "bedroomCount": 2, "bathroomCount": 2},
            ],
            "availableUnits": [{
                "unitId": "11068788", "unitNumber": "12F", "floorPlanId": "p1",
                "area": 468, "minPrice": 3840, "availableOn": "2026-08-08",
                "minBaseRentLeaseTerm": "12",
            }],
        }
        rows = GreystarAdapter._parse_property(
            property_data, "https://example.test/search", "2026-08-08T00:00:00+00:00"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_id"], "gs-21037-11068788")
        self.assertEqual(rows[0]["address"], "345 East 94th St")
        self.assertEqual(rows[0]["unit_number"], "12F")
        self.assertEqual(rows[0]["bedrooms"], 1)
        self.assertEqual(rows[0]["bathrooms"], 1)
        raw = json.loads(rows[0]["raw_json"])
        self.assertEqual(raw["source_url"], "https://www.greystar.com/api/property/21037")
        self.assertEqual(raw["available_unit"]["unitNumber"], "12F")

    def test_rejects_non_nyc_property_and_count_only_floorplans(self):
        property_data = {
            "id": "1",
            "location": {"address": "1 Main St", "city": "White Plains", "postalCode": "10606"},
            "floorplans": [{"id": "p1", "bedroomCount": 1}],
            "availableUnits": [],
        }
        self.assertEqual(GreystarAdapter._parse_property(property_data, "", ""), [])


if __name__ == "__main__":
    unittest.main()
