import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from tools.merges.mine_dwelling_unit_description_delta import (
    SOURCES,
    normalize_bbl,
    observed_date,
    query,
    where_clause,
)


class DwellingUnitDescriptionDeltaTest(unittest.TestCase):
    def test_normalizes_direct_and_component_bbls(self):
        self.assertEqual(normalize_bbl("1018900040.0"), "1018900040")
        self.assertEqual(normalize_bbl("BROOKLYN", "1898", "41"), "3018980041")
        self.assertEqual(normalize_bbl("bad", "1", "1"), "")

    def test_normalizes_source_dates(self):
        self.assertEqual(observed_date("2025-04-02T00:00:00.000"), "2025-04-02")
        self.assertEqual(observed_date("20250402", compact=True), "2025-04-02")
        self.assertEqual(observed_date("bad", compact=True), "")

    def test_filter_is_delta_only(self):
        clause = where_clause(SOURCES["approved_permit"])
        self.assertIn("DWELLING+UNIT", clause.replace(" ", "+"))
        self.assertIn("RESIDENTIAL+UNIT", clause.replace(" ", "+"))
        self.assertIn("AND NOT", clause)
        self.assertIn("APT%23", urlencode({"q": clause}))

    @patch("tools.merges.mine_dwelling_unit_description_delta.urlopen")
    def test_query_uses_source_dataset_and_bounded_page(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = b"[]"
        self.assertEqual(query(SOURCES["dcp"], 25, 100), [])
        url = urlopen.call_args.args[0].full_url
        self.assertIn("/br6q-ssj3.json", url)
        self.assertIn("%24limit=100", url)
        self.assertIn("%24offset=25", url)


if __name__ == "__main__":
    unittest.main()
