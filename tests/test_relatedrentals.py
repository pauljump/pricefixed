import json
import unittest

from pricefixed.adapters.relatedrentals import RelatedRentalsAdapter


class RelatedRentalsAdapterTest(unittest.TestCase):
    def test_requires_detail_unit_id_and_exact_address(self):
        html = '''
        <script type="application/json" data-drupal-selector="drupal-settings-json">
        {"entity":{"id":"11991","unit_id":"04H","unit_property_name":"Abington House"},
         "visited_node_info":{"availability_price":"7995"},
         "gtmUnitDetail":{"brand":"New York City","category":"Hudson Yards","dimension6":"1.0","dimension7":"1.0"}}
        </script>
        <div class="fg-unit-header__property-label"><strong>Abington House</strong> | 500 West 30th Street New York, NY 10001</div>
        <dd class="unit-availability__value">Available 09/15</dd>
        '''
        row = RelatedRentalsAdapter._parse_detail(
            html, "https://example.test/unit/26302", bbl="1007017502",
            bbl_evidence={"source": "dob_now_job_filings", "rows": []},
        )
        self.assertEqual(row["source_id"], "related-11991")
        self.assertEqual(row["address"], "500 West 30th Street")
        self.assertEqual(row["unit_number"], "04H")
        self.assertEqual(row["zipcode"], "10001")
        self.assertEqual(row["price"], 7995)
        self.assertEqual(row["bedrooms"], 1.0)
        self.assertEqual(row["available_date"], "Available 09/15")
        raw = json.loads(row["raw_json"])
        self.assertEqual(raw["entity"]["unit_id"], "04H")
        self.assertEqual(raw["bbl"], "1007017502")

    def test_search_parser_keeps_detail_links_and_ids(self):
        html = '''<article class="node node--type-unit node--view-mode-teaser" data-api-id="26302" data-price="7995">
        <a href="/unit/26302" class="field-group-link">Unit</a></article>'''
        rows = RelatedRentalsAdapter._teasers(html, "https://example.test/search?page=0")
        self.assertEqual(rows[0]["api_id"], "26302")
        self.assertEqual(rows[0]["url"], "https://example.test/unit/26302")

    def test_rejects_missing_unit_or_address(self):
        html = '''<script type="application/json" data-drupal-selector="drupal-settings-json">
        {"entity":{"id":"1","unit_property_name":"Abington House"}}</script>
        <div class="fg-unit-header__property-label">Abington House</div>'''
        self.assertIsNone(RelatedRentalsAdapter._parse_detail(html, "https://example.test/unit/1"))


if __name__ == "__main__":
    unittest.main()
