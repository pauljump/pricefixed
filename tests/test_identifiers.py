import unittest

from pricefixed.engine.identifiers import normalize_bbl


class IdentifierNormalizationTest(unittest.TestCase):
    def test_accepts_canonical_and_decimal_bbls(self):
        self.assertEqual(normalize_bbl("1009780001"), "1009780001")
        self.assertEqual(normalize_bbl("1009780001.00000000"), "1009780001")

    def test_repairs_known_legacy_extra_lot_zero(self):
        self.assertEqual(normalize_bbl("10097800001"), "1009780001")

    def test_rejects_ambiguous_lengths(self):
        self.assertIsNone(normalize_bbl("10097810001"))
        self.assertIsNone(normalize_bbl("BBL 1009780001"))
        self.assertIsNone(normalize_bbl("bad"))
