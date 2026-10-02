import unittest

from tools.merges.mine_dob_violation_description_units import compact_date, make_bbl
from tools.merges.mine_hpd_work_description_units import normalize_bbl, observed_date


class RemainingDescriptionTest(unittest.TestCase):
    def test_normalizes_dob_identity_fields(self):
        self.assertEqual(make_bbl("1", "00543", "00019"), "1005430019")
        self.assertEqual(compact_date("19881207"), "1988-12-07")
        self.assertEqual(compact_date("19881340"), "")

    def test_normalizes_hpd_identity_fields(self):
        self.assertEqual(normalize_bbl("4015120026.0"), "")
        self.assertEqual(normalize_bbl("4015120026"), "4015120026")
        self.assertEqual(observed_date("2012-11-15T00:00:00.000"), "2012-11-15")
        self.assertEqual(observed_date(""), "")
