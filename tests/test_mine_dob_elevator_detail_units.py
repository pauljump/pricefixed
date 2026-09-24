import sqlite3
import unittest
from unittest.mock import patch

from tools.merges.mine_dob_elevator_detail_units import query, resolve_pad_bbl


class DobElevatorDetailTest(unittest.TestCase):
    def setUp(self):
        self.catalog = sqlite3.connect(":memory:")
        self.catalog.execute(
            "CREATE TABLE addresses (bbl TEXT, normalized TEXT, source TEXT)"
        )

    def tearDown(self):
        self.catalog.close()

    def test_resolves_only_one_exact_pad_address(self):
        self.catalog.execute(
            "INSERT INTO addresses VALUES (?,?,?)",
            ("3023680018", "346 METROPOLITAN AVE", "nyc_pad"),
        )
        self.catalog.execute(
            "INSERT INTO addresses VALUES (?,?,?)",
            ("9999999999", "346 METROPOLITAN AVE", "other"),
        )
        self.assertEqual(
            resolve_pad_bbl(self.catalog, "346 Metropolitan Avenue"), "3023680018"
        )
        self.catalog.execute(
            "INSERT INTO addresses VALUES (?,?,?)",
            ("3023680019", "346 METROPOLITAN AVE", "nyc_pad"),
        )
        self.assertEqual(resolve_pad_bbl(self.catalog, "346 Metropolitan Avenue"), "")

    @patch("tools.merges.mine_dob_elevator_detail_units.urlopen")
    def test_query_is_bounded_to_apartment_markers(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = b"[]"

        self.assertEqual(query(0, 100), [])
        url = urlopen.call_args.args[0].full_url
        self.assertIn("device_job_description", url)
        self.assertIn("device_id%2Cphysical_address", url)


if __name__ == "__main__":
    unittest.main()
