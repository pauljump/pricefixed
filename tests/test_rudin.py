import json
import unittest

from pricefixed.adapters.rudin import RudinAdapter


class RudinAdapterTest(unittest.TestCase):
    def test_keeps_explicit_listing_and_uses_parent_exact_address(self):
        payload = [
            {"type": "Property", "nid": "8", "title": "136 East 55th Street",
             "field_address": "136 East 55th Street", "field_neighborhood": "Midtown",
             "field_latitude": "40.76", "field_longitude": "-73.97"},
            {"type": "Listing", "nid": "295", "title": "4N", "field_property": "8",
             "field_availability": "On", "field_bedrooms": "0",
             "field_bathrooms": "1.0", "field_maximum_rent": "$4,095.00",
             "field_availability_date": '<time datetime="2026-07-21T17:00:31-04:00">Tue</time>',
             "field_short_description": "Premium Appliances"},
        ]
        rows = RudinAdapter._parse_payload(payload, "https://example.test/availability",
                                            "https://example.test/api/properties-json",
                                            "2026-08-08T00:00:00+00:00")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_id"], "rudin-295")
        self.assertEqual(rows[0]["building_name"], "136 East 55th Street")
        self.assertEqual(rows[0]["address"], "136 East 55th Street")
        self.assertEqual(rows[0]["unit_number"], "4N")
        self.assertEqual(rows[0]["price"], 4095)
        self.assertEqual(rows[0]["available_date"], "2026-07-21T17:00:31-04:00")
        raw = json.loads(rows[0]["raw_json"])
        self.assertEqual(raw["feed_url"], "https://example.test/api/properties-json")

    def test_rejects_properties_floorplans_and_unavailable_rows(self):
        payload = [
            {"type": "Property", "nid": "8", "title": "136 East 55th Street",
             "field_address": "136 East 55th Street"},
            {"type": "Property", "nid": "9", "title": "No Address", "field_address": ""},
            {"type": "Listing", "nid": "1", "title": "Floor Plan A", "field_property": "8",
             "field_availability": "Off"},
            {"type": "Listing", "nid": "2", "title": "Unknown", "field_property": "9",
             "field_availability": "On"},
        ]
        self.assertEqual(RudinAdapter._parse_payload(payload), [])


if __name__ == "__main__":
    unittest.main()
