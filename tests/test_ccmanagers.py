import json
import unittest

from pricefixed.adapters.ccmanagers import parse_availability


class CCManagersParserTest(unittest.TestCase):
    def test_parses_public_table_with_exact_unit_url(self):
        html = """
        <table><thead><tr><th>Building</th><th>Unit</th><th>Beds</th><th>Baths</th>
        <th>Rent</th><th>Date Available</th></tr></thead><tbody>
        <tr><td><a href="/?post_type=properties&amp;p=147832">55 South Essex Avenue</a></td>
        <td><a href="/properties/55-south-essex-avenue/507">507</a></td>
        <td>3</td><td>2</td><td>$2,100.00</td><td>Immediately</td></tr>
        </tbody></table>
        """
        rows = parse_availability(html)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["address"], "55 South Essex Avenue")
        self.assertEqual(rows[0]["unit_number"], "507")
        self.assertEqual(rows[0]["price"], 2100.0)
        raw = json.loads(rows[0]["raw_json"])
        self.assertEqual(raw["source_url"], "https://ccmanagers.com/availability/")
        self.assertTrue(raw["unit_url"].endswith("/properties/55-south-essex-avenue/507"))


if __name__ == "__main__":
    unittest.main()
