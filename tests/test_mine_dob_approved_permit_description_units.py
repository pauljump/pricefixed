import unittest
from unittest.mock import patch

from tools.merges.mine_dob_approved_permit_description_units import normalize_bbl, observed_date, query


class DobApprovedPermitDescriptionTest(unittest.TestCase):
    def test_normalizes_identity_fields(self):
        self.assertEqual(normalize_bbl("4033550106"), "4033550106")
        self.assertEqual(normalize_bbl("bad"), "")
        self.assertEqual(observed_date("2024-11-18T00:00:00.000"), "2024-11-18")

    @patch("tools.merges.mine_dob_approved_permit_description_units.urlopen")
    def test_query_excludes_rows_with_direct_apartment_field(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = b"[]"
        self.assertEqual(query(0, 100), [])
        url = urlopen.call_args.args[0].full_url
        self.assertIn("apt_condo_no_s+is+null", url)
        self.assertIn("work_permit%2Csequence_number", url)
