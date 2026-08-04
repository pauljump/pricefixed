import unittest
from unittest.mock import patch

from tools.merges.mine_additional_official_description_units import (
    SOURCES,
    normalize_bbl,
    observed_date,
    query,
    where_clause,
)


class AdditionalOfficialDescriptionTest(unittest.TestCase):
    def test_normalizes_direct_bbl_and_dates(self):
        self.assertEqual(normalize_bbl("1011717508.0"), "1011717508")
        self.assertEqual(normalize_bbl("Brooklyn", "1241", "58"), "3012410058")
        self.assertEqual(normalize_bbl("bad"), "")
        self.assertEqual(observed_date("2025-06-16T00:00:00.000"), "2025-06-16")
        self.assertEqual(observed_date("06/16/2025"), "2025-06-16")

    def test_hpd_filter_requires_blank_structured_apartment(self):
        clause = where_clause(SOURCES["hpd_violation_blank"])
        self.assertIn("apartment is null", clause)
        self.assertIn("novdescription", clause)

    def test_landmark_complaints_use_tax_lot_components(self):
        config = SOURCES["landmark_complaint"]
        self.assertEqual(config["bbl"], ("borough", "block", "lot"))
        self.assertIn("block is not null", where_clause(config))

    @patch("tools.merges.mine_additional_official_description_units.urlopen")
    def test_laa_query_uses_compound_stable_order(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = b"[]"
        self.assertEqual(query(SOURCES["laa"], 0, 100), [])
        url = urlopen.call_args.args[0].full_url
        self.assertIn("/xxbr-ypig.json", url)
        self.assertIn("job_number%2Cfiling_number%2Cpermit_number", url)


if __name__ == "__main__":
    unittest.main()
