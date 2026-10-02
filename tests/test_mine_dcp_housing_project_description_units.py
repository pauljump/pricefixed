import unittest
from unittest.mock import patch

from tools.merges.mine_dcp_housing_project_description_units import (
    normalize_bbl,
    observed_date,
    query,
)


class DcpHousingProjectDescriptionTest(unittest.TestCase):
    def test_normalizes_identity_fields(self):
        self.assertEqual(normalize_bbl("1004060059.0"), "1004060059")
        self.assertEqual(normalize_bbl("bad"), "")
        self.assertEqual(observed_date("2024-02-29T00:00:00.000"), "2024-02-29")
        self.assertEqual(observed_date("not-a-date"), "")

    @patch("tools.merges.mine_dcp_housing_project_description_units.urlopen")
    def test_query_is_bounded_to_apartment_markers(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = b"[]"

        self.assertEqual(query(0, 100), [])
        url = urlopen.call_args.args[0].full_url
        self.assertIn("job_desc", url)
        self.assertIn("job_number%2Cbbl%2Caddressnum", url)


if __name__ == "__main__":
    unittest.main()
