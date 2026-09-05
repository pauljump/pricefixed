import json
import unittest

from pricefixed.adapters.lisamgmt import parse_residential_page


class LisaManagementParserTest(unittest.TestCase):
    def test_parses_next_data_exact_address_and_unit(self):
        payload = {
            "props": {
                "pageProps": {
                    "pagesNumber": 1,
                    "apartments": [
                        {
                            "id": 174560,
                            "unitNumber": "4K",
                            "bedrooms": "1 Bedroom",
                            "bathrooms": "1 Bath",
                            "rent": 3795,
                            "squareFeet": 650,
                            "image": "https://example.test/4k.jpg",
                            "property": {
                                "name": "22 Caton Place",
                                "address": "22 Caton Place",
                                "city": "Brooklyn",
                                "state": "NY",
                                "zip": "11218",
                                "neighborhood": {"name": "Kensington"},
                            },
                        }
                    ],
                }
            }
        }
        html = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(payload) + "</script>"
        rows, pages = parse_residential_page(html, "https://www.lisamgmt.com/residential", "2026-08-08T12:00:00+00:00")
        self.assertEqual(pages, 1)
        self.assertEqual(rows[0]["address"], "22 Caton Place")
        self.assertEqual(rows[0]["unit_number"], "4K")
        self.assertEqual(rows[0]["bedrooms"], 1)
        self.assertEqual(rows[0]["price"], 3795.0)
        self.assertEqual(json.loads(rows[0]["raw_json"])["api_item"]["id"], 174560)


if __name__ == "__main__":
    unittest.main()
