import json
import unittest

from pricefixed.adapters.udr import UDRAdapter, parse_pricing_page, pricing_urls


class UDRAdapterTest(unittest.TestCase):
    def test_pricing_urls_are_unique(self):
        html = '<a href="/x/apartments-pricing/">A</a><a href="/x/apartments-pricing/">B</a>'
        self.assertEqual(pricing_urls(html), ["https://www.udr.com/x/apartments-pricing/"])

    def test_keeps_explicit_jsonld_units_not_floorplan_counts(self):
        html = """
        <span class="prop-address"><span>808 Columbus Ave</span>, <span>New York</span>,
        <span>NY</span> <span>10025</span></span>
        <script type="application/ld+json">
        {"itemListElement":[
          {"item":{"name":"Apartment #775 - 11E", "url":"https://www.udr.com/x/apartments-pricing/?unitid=123",
            "offers":{"price":3966}, "floorSize":{"value":414}, "numberOfBedrooms":0,
            "numberOfBathroomsTotal":1}},
          {"item":{"name":"Studio floorplan", "offers":{"price":3000}}}
        ]}
        </script>
        """
        rows = parse_pricing_page(
            html, "https://www.udr.com/x/apartments-pricing/", "2026-08-09T00:00:00Z",
            crosswalk_fn=lambda address, retrieved_at: ("1018527501", {
                "source": "dob_now_job_filings", "rows": []
            }),
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_id"], "udr-x-123")
        self.assertEqual(rows[0]["unit_number"], "11E")
        self.assertEqual(rows[0]["address"], "808 Columbus Ave")
        self.assertEqual(rows[0]["price"], 3966)
        raw = json.loads(rows[0]["raw_json"])
        self.assertEqual(raw["extraction_method"], "official_udr_apartment_jsonld")
        self.assertEqual(raw["source_address"], "808 Columbus Ave, New York, NY 10025")
        self.assertEqual(raw["bbl"], "1018527501")


if __name__ == "__main__":
    unittest.main()
