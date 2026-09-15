import unittest

from tools.merges.mine_dob_electrical_description_units import normalize_bbl, observed_date


class DobElectricalDescriptionTest(unittest.TestCase):
    def test_normalizes_identity_fields(self):
        self.assertEqual(normalize_bbl("1004060059"), "1004060059")
        self.assertEqual(normalize_bbl("bad"), "")
        self.assertEqual(observed_date("2018-04-18T00:00:00.000"), "2018-04-18")
        self.assertEqual(observed_date(""), "")
