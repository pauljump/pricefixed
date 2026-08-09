import json
import unittest

from pricefixed.adapters.spherexx import SpherexxAdapter, _unit_rows


class SpherexxParserTest(unittest.TestCase):
    def test_parses_exact_address_and_unit_from_ajax_row(self):
        html = """
        <div class="unit-list-item body-subtext transition" data-building-name="Cadillac" data-page="1"
             data-num-in-page="1" data-url="/availability/building/residence-4l/"
             data-uid="56340" data-base-price="2525">
          <button aria-label="4L in Cadillac on 123-60 83rd Avenue, Studio 1 Bathroom, 490 square feet, $2,525, Available Now">
            <span class="text-bold">Cadillac <span>4L</span></span>
            <span class="unit-list-address"><nobr>123-60 83rd Avenue</nobr></span>
            <span class="hidden--mobile unit-date-available">Available Now</span>
          </button>
        </div></div></div>
        """
        rows = _unit_rows(
            html,
            {"label": "test"},
            "https://example.com/availability/",
            "https://example.com/ajax/getunitlist.asp",
            "2026-08-08T12:00:00+00:00",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["address"], "123-60 83rd Avenue")
        self.assertEqual(rows[0]["unit_number"], "4L")
        self.assertEqual(rows[0]["bedrooms"], 0)
        self.assertEqual(rows[0]["sqft"], 490)
        self.assertEqual(rows[0]["price"], 2525)
        raw = json.loads(rows[0]["raw_json"])
        self.assertEqual(raw["source_url"], "https://example.com/availability/")
        self.assertEqual(raw["feed_url"], "https://example.com/ajax/getunitlist.asp")

    def test_payload_is_paged_and_post_safe(self):
        payload = SpherexxAdapter._payload(2).decode()
        self.assertIn("page=2", payload)
        self.assertIn("numberPerPage=10", payload)


if __name__ == "__main__":
    unittest.main()
