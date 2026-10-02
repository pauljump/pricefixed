import json
import unittest

from pricefixed.adapters.olnick import parse_project_page, project_urls


class OlnickParserTest(unittest.TestCase):
    def test_follows_explicit_project_pages(self):
        html = '<a class="project-item" href="/r/example">view</a><a href="/r/nope">no</a>'
        self.assertEqual(project_urls(html), ["https://olnickrentals.com/r/example"])

    def test_parses_exact_address_and_unit(self):
        html = """
        <div class="apartment-item"><div class="left">
          <div class="name">The Devonshire - – 40 West 135th Street – Apt # 03A</div>
          <div class="params"><div class="item">1 bedroom / 1 bathroom</div>
          <div class="item">736 sq ft</div><div class="item">$2,800.00</div></div>
        </div><div class="right"><a href="/u/6493499390?building_id=example">view details</a></div></div>
        """
        rows = parse_project_page(html, "https://olnickrentals.com/r/example", "2026-08-08T12:00:00+00:00")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["address"], "40 West 135th Street")
        self.assertEqual(rows[0]["unit_number"], "03A")
        self.assertEqual(rows[0]["bedrooms"], 1)
        self.assertEqual(rows[0]["bathrooms"], 1.0)
        self.assertEqual(rows[0]["price"], 2800.0)
        self.assertEqual(json.loads(rows[0]["raw_json"])["unit_detail_url"], "https://olnickrentals.com/u/6493499390?building_id=example")


if __name__ == "__main__":
    unittest.main()
