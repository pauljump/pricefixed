"""Regression tests for the MLS display-address fallback."""
import unittest

from pricefixed.adapters.elliman import _address_and_unit


class EllimanAddressTest(unittest.TestCase):
    def test_extracts_embedded_unit_and_strips_city(self):
        address, unit = _address_and_unit({
            "samlsFullAddress": "211 W 10th St 2B, New York, NY 10014",
            "unitNumber": None,
        })
        self.assertEqual(address, "211 W 10th St")
        self.assertEqual(unit, "2B")

    def test_preserves_lettered_avenue(self):
        address, unit = _address_and_unit({
            "samlsFullAddress": "622 Avenue B, New York, NY 10009",
            "unitNumber": None,
        })
        self.assertEqual(address, "622 Avenue B")
        self.assertIsNone(unit)

    def test_prefers_explicit_unit_field(self):
        address, unit = _address_and_unit({
            "samlsFullAddress": "1420 York Ave 3H, New York, NY 10021",
            "unitNumber": "3H",
        })
        self.assertEqual(address, "1420 York Ave")
        self.assertEqual(unit, "3H")
