import json
import unittest

from pricefixed.adapters.securecafe import SecureCafeAdapter


class SecureCafeParserTest(unittest.TestCase):
    def test_parses_current_rentcafe_rows_and_preserves_source(self):
        html = """
        <div class="block"><caption class="sr-only">Apartment Details and Selection for Floor Plan: A1 - 1 Bedroom, 1 Bathroom</caption>
        <table><tr class="AvailUnitRow" id="unitrow_123">
          <th data-label='Apartment'>#18D</th>
          <td data-label=Sq.Ft.>631</td>
          <td data-label='Rent'>$5,942-$8,692</td>
          <td data-label='Date Available'><span>8/29/2026</span></td>
          <td><input id='18D' onclick='ApplyNowClick("123","456","789","8/29/2026","terms")'></td>
        </tr></table></div>
        """
        portal = {
            "label": "The Capitol (Bozzuto)",
            "subdomain": "thecapitolchelsea",
            "slug": "the-capitol",
            "address": "776 Sixth Avenue",
            "hood": "Chelsea",
            "boro": "Manhattan",
            "source_url": "https://www.bozzuto.com/apartments-for-rent/ny/new-york/the-capitol",
        }
        rows = SecureCafeAdapter()._parse_portal_html(
            html,
            portal,
            "https://thecapitolchelsea.securecafe.com/onlineleasing/the-capitol/availableunits.aspx",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["address"], "776 Sixth Avenue")
        self.assertEqual(rows[0]["unit_number"], "18D")
        self.assertEqual(rows[0]["price"], 5942)
        self.assertEqual(rows[0]["available_date"], "8/29/2026")
        raw = json.loads(rows[0]["raw_json"])
        self.assertEqual(raw["source_url"], portal["source_url"])


if __name__ == "__main__":
    unittest.main()
