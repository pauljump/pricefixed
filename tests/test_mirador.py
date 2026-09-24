import json
import unittest

from pricefixed.adapters.mirador import MiradorAdapter


class MiradorAdapterTest(unittest.TestCase):
    def test_keeps_explicit_nyc_unit_and_raw_graphql_provenance(self):
        rows = [{
            "id": "unit-1",
            "name": "270 Park Avenue S 8C",
            "status": "For Lease",
            "addressLine1": "270 Park Avenue S 8C",
            "addressCity": "New York City",
            "addressState": "NY",
            "postalCode": "10010",
            "leasePrice": 5850,
            "leasePeriod": "MONTH",
            "bedroomCount": 1,
            "bathCount": 1,
            "livingSpaceSize": "700.0",
            "slug": "270-park-avenue-s-8c",
        }]
        parsed = MiradorAdapter._parse_rows(
            rows,
            "https://example.test/properties",
            "https://example.test/graphql",
            "2026-08-09T00:00:00+00:00",
            "query test",
            {"offset": 0},
        )
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["source_id"], "mirador-unit-1")
        self.assertEqual(parsed[0]["address"], "270 Park Avenue S")
        self.assertEqual(parsed[0]["unit_number"], "8C")
        self.assertEqual(parsed[0]["price"], 5850)
        raw = json.loads(parsed[0]["raw_json"])
        self.assertEqual(raw["detail_url"], "https://miradorrealestate.com/properties/270-park-avenue-s-8c")
        self.assertEqual(raw["feed_url"], "https://example.test/graphql")
        self.assertEqual(raw["listed_address"], "270 Park Avenue S 8C")
        self.assertEqual(raw["api_record"]["id"], "unit-1")

    def test_rejects_non_nyc_and_missing_explicit_unit(self):
        rows = [
            {
                "id": "building-only",
                "addressLine1": "60 W 23rd Street",
                "addressCity": "New York City",
                "addressState": "NY",
            },
            {
                "id": "connecticut-unit",
                "addressLine1": "504 Glenbrook Road 310",
                "addressCity": "Stamford",
                "addressState": "CT",
            },
        ]
        self.assertEqual(MiradorAdapter._parse_rows(rows), [])


if __name__ == "__main__":
    unittest.main()
