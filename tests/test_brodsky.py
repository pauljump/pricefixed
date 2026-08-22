import json
import unittest

from pricefixed.adapters.brodsky import listing_urls, parse_listing_page


class BrodskyParserTest(unittest.TestCase):
    def test_follows_only_explicit_apartment_links(self):
        html = (
            '<a href="/rentals/upper-west-side/building/building-apartment-705">live</a>'
            '<a href="/rentals/upper-west-side/building">building</a>'
        )
        self.assertEqual(
            listing_urls(html),
            ["https://www.brodsky.com/rentals/upper-west-side/building/building-apartment-705"],
        )

    def test_parses_jsonld_exact_address_and_unit(self):
        html = r'''
        <script type="application/ld+json">
        {"@type":"RealEstateListing","name":"499 President - Apartment 518",
         "description":"Studio","address":{"streetAddress":"499 President Street, Unit 518",
         "addressLocality":"Brooklyn","postalCode":"11215"},
         "mainEntity":{"@type":"Apartment","name":"518"},
         "offers":{"price":3208,"availability":"https://schema.org/InStock"}}
        </script>
        <script>self.__next_f.push([1,"{\\"bedrooms\\":\\"Studio\\",\\"bathrooms\\":\\"1\\",\\"availableDate\\":\\"Now\\"}"])</script>
        '''
        row = parse_listing_page(html, "https://www.brodsky.com/rentals/gowanus/building/apartment-518")
        self.assertEqual(row["address"], "499 President Street")
        self.assertEqual(row["unit_number"], "518")
        self.assertEqual(row["bedrooms"], 0)
        self.assertEqual(row["bathrooms"], 1.0)
        self.assertEqual(row["price"], 3208)
        self.assertEqual(json.loads(row["raw_json"])["source_url"], row["raw_json"] and "https://www.brodsky.com/rentals/gowanus/building/apartment-518")


if __name__ == "__main__":
    unittest.main()
