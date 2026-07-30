"""Regression tests for source-provided street and unit labels."""
import unittest

from pricefixed.adapters.appfolio import _parse_address
from pricefixed.adapters.avalonbay import _split_address_unit
from pricefixed.adapters.nooklyn import NooklynAdapter


class ListingAddressParsingTest(unittest.TestCase):
    def test_avalonbay_removes_apartment_suffix(self):
        self.assertEqual(
            _split_address_unit("343 Gold Street Apartment 1816"),
            ("343 Gold Street", "1816"),
        )

    def test_avalonbay_keeps_plain_street(self):
        self.assertEqual(_split_address_unit("10 Main Street"), ("10 Main Street", None))

    def test_appfolio_reads_comma_delimited_apartment(self):
        self.assertEqual(
            _parse_address("288 Troutman Street, Apt 2L, Brooklyn, NY 11237"),
            ("288 Troutman Street", "2L", "Brooklyn", "11237"),
        )

    def test_appfolio_reads_comma_delimited_suite(self):
        self.assertEqual(
            _parse_address("144 North 7th Street, Suite 408, Brooklyn, NY 11249"),
            ("144 North 7th Street", "408", "Brooklyn", "11249"),
        )

    def test_nooklyn_v3_listing_keeps_street_and_unit_separate(self):
        listing = NooklynAdapter()._map({
            "id": 96287,
            "price": 372500,
            "address": "11-24 31st Dr, Astoria, NY 11106, USA",
            "short_address": "11-24 31st Dr - Unit: 8G",
            "bedrooms": 2,
            "bathrooms": 1,
            "neighborhood": {"name": "Astoria"},
        })
        self.assertEqual(listing["source_id"], "96287")
        self.assertEqual(listing["address"], "11-24 31st Dr")
        self.assertEqual(listing["unit_number"], "8G")
        self.assertEqual(listing["zipcode"], "11106")
        self.assertEqual(listing["borough"], "Queens")
        self.assertEqual(listing["price"], 3725)


if __name__ == "__main__":
    unittest.main()
