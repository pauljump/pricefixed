import json
import unittest

from pricefixed.adapters.rockrose import building_urls, parse_building_page


class RockroseAdapterTest(unittest.TestCase):
    def test_building_urls_are_unique(self):
        html = '<a href="/building/linc-lic/">Linc</a><a href="/building/linc-lic">again</a>'
        self.assertEqual(building_urls(html), ["https://rockrose.com/building/linc-lic"])

    def test_parses_explicit_cards_and_deduplicates_mobile_copy(self):
        html = """
        <h1 id="HeroFancyTitle">Linc LIC</h1>
        <span class="property-details__street">43-10 Crescent Street</span>
        <span class="property-details__city-state-zip">Queens, NY 11101</span>
        <div class="grid-card__listing-card"><span class='address'>43-10 Crescent Street,<br>Queens, NY 11101</span>
          <li class='price'>$3,625</li><li class='size'>Studio, 1 Bath</li>
          <a href="https://rockrose.com/listing/2909/" data-popup-unit-number="2909"></a></div>
        <div class="grid-card__listing-card"><span class='address'>43-10 Crescent Street</span>
          <li class='price'>$3,625</li><li class='size'>Studio, 1 Bath</li>
          <a href="https://rockrose.com/listing/2909/" data-popup-unit-number="2909"></a></div>
        """
        rows = parse_building_page(
            html, "https://rockrose.com/building/linc-lic", "2026-08-09T00:00:00Z",
            crosswalk_fn=lambda address, retrieved_at: (None, None),
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["unit_number"], "2909")
        self.assertEqual(rows[0]["address"], "43-10 Crescent Street")
        self.assertEqual(rows[0]["bedrooms"], 0)
        self.assertEqual(rows[0]["price"], 3625.0)
        raw = json.loads(rows[0]["raw_json"])
        self.assertEqual(raw["extraction_method"], "official_rockrose_html_selected_listing")
        self.assertEqual(raw["source_address"], "43-10 Crescent Street, Queens, NY 11101")


if __name__ == "__main__":
    unittest.main()
