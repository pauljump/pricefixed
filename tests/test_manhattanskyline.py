import json
import unittest

from pricefixed.adapters.manhattanskyline import parse_unit_page


class ManhattanSkylineParserTest(unittest.TestCase):
    def setUp(self):
        self.item = {
            "number": "18F",
            "slug": "2l2dzmap",
            "square_footage": None,
            "bedrooms": 0,
            "bathrooms": 1,
            "price": "4295.00",
            "body": "Studio description",
            "available_on": None,
            "building": {
                "name": "The Murray Hill<sup>®</sup>",
                "neighborhood": {"name": "Murray Hill"},
                "address": {"latLng": {"lat": 40.7468, "lng": -73.9801}},
            },
        }

    def test_requires_exact_numeric_street_address(self):
        html = (
            '<address class="detail__info--copy">115 East 34 Street<br/>'
            'New York, NY 10016<br/><a href="/building">view building</a></address>'
        )
        row = parse_unit_page(html, self.item, "https://manhattanskyline.com/unit/2l2dzmap")
        self.assertEqual(row["address"], "115 East 34 Street")
        self.assertEqual(row["unit_number"], "18F")
        self.assertEqual(row["zipcode"], "10016")
        self.assertEqual(row["price"], 4295.0)
        self.assertEqual(json.loads(row["raw_json"])["feed_url"], "https://manhattanskyline.com/api/units")

    def test_rejects_building_name_without_street_address(self):
        html = (
            '<address class="detail__info--copy">Manhattan East<br/>'
            'New York, NY 10065<br/></address>'
        )
        self.assertIsNone(parse_unit_page(html, self.item, "https://example.test/unit"))


if __name__ == "__main__":
    unittest.main()
