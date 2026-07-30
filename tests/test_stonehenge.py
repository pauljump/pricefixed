"""Stonehenge property-code address mapping regression tests."""
import unittest

from pricefixed.adapters.stonehenge import BUILDING_ADDRESSES


class StonehengeAddressTest(unittest.TestCase):
    def test_known_codes_have_operator_addresses(self):
        self.assertEqual(BUILDING_ADDRESSES["354e91ow"], "354 East 91st Street")
        self.assertEqual(BUILDING_ADDRESSES["oneqps"], "42-20 24th Street")

    def test_unknown_code_is_not_inferred(self):
        self.assertIsNone(BUILDING_ADDRESSES.get("future-building"))
