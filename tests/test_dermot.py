import json
import unittest

from pricefixed.adapters.dermot import _map_listing


class DermotAdapterTest(unittest.TestCase):
    def test_maps_exact_address_and_unit_with_source_provenance(self):
        prop = {
            "community_id": 3387,
            "url": "https://www.dermotcompany.com/building/the-addison",
        }
        listing = _map_listing(
            {
                "id": 5217390,
                "unit_number": "11K",
                "price": "3155.00",
                "date_available": "2026-08-25T00:00:00.000Z",
                "bedrooms": 0,
                "bathrooms": 1.0,
                "square_footage": 426,
                "building": {
                    "name": "The Addison",
                    "street_address": "225 Schermerhorn Street",
                    "state": "NY",
                    "city": "Brooklyn",
                    "postal_code": "11201",
                },
            },
            prop,
            "2026-08-08T12:00:00+00:00",
        )
        self.assertEqual(listing["address"], "225 Schermerhorn Street")
        self.assertEqual(listing["unit_number"], "11K")
        self.assertEqual(listing["price"], 3155.0)
        self.assertEqual(listing["available_date"], "2026-08-25")
        raw = json.loads(listing["raw_json"])
        self.assertEqual(raw["_pricefixed_source_url"], prop["url"])
        self.assertIn("property=3387", raw["_pricefixed_feed_url"])

    def test_rejects_missing_unit_or_non_new_york_rows(self):
        prop = {"community_id": 1, "url": "https://example.test/building"}
        base = {"id": 1, "unit_number": "", "building": {"street_address": "1 Main Street", "state": "NY"}}
        self.assertIsNone(_map_listing(base, prop, "2026-08-08T00:00:00+00:00"))
        base["unit_number"] = "2A"
        base["building"]["state"] = "FL"
        self.assertIsNone(_map_listing(base, prop, "2026-08-08T00:00:00+00:00"))


if __name__ == "__main__":
    unittest.main()
