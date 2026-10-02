import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tools.merges.import_securecafe_browser_capture import build_listings, import_capture


class SecureCafeBrowserCaptureTest(unittest.TestCase):
    def test_builds_only_explicit_rows_and_keeps_provenance(self):
        capture = {
            "retrieved_at": "2026-08-09T03:21:56Z",
            "sources": [{
                "property": "19 Dutch",
                "address": "19 Dutch St, New York, NY 10038",
                "official_url": "https://www.bozzuto.com/apartments-for-rent/ny/new-york/19-dutch",
                "availability_url": "https://19dutch.securecafe.com/onlineleasing/19-dutch/availableunits.aspx",
                "rows": [
                    {"unit": "#30H", "sqft": "694", "rent": "$5,941-$6,027",
                     "available": "9/20/2026", "caption": "1 Bedroom, 1 Bathroom"},
                    {"unit": "", "sqft": "700", "rent": "$6,000", "caption": "1 Bedroom"},
                ],
            }],
        }
        rows, rejected = build_listings(capture)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_id"], "sc-19dutch-30H")
        self.assertEqual(rows[0]["address"], "19 Dutch St")
        self.assertEqual(rows[0]["zipcode"], "10038")
        self.assertEqual(rows[0]["price"], 5941.0)
        self.assertEqual(rows[0]["bedrooms"], 1)
        self.assertEqual(rows[0]["bathrooms"], 1.0)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["rejection_reason"], "missing_explicit_unit_label")
        raw = json.loads(rows[0]["raw_json"])
        self.assertEqual(raw["availability_url"], capture["sources"][0]["availability_url"])
        self.assertEqual(raw["extraction_method"], "browser_visible_dom_table")

    def test_imports_into_normal_listings_schema(self):
        capture = {
            "retrieved_at": "2026-08-09T03:21:56Z",
            "sources": [{
                "property": "Aalto57",
                "address": "1065 2nd Ave, New York, NY 10022",
                "official_url": "https://www.bozzuto.com/apartments-for-rent/ny/new-york/aalto57",
                "availability_url": "https://aalto57.securecafe.com/onlineleasing/aalto57/availableunits.aspx",
                "rows": [{"unit": "#06F", "sqft": "705", "rent": "$6,450",
                          "available": "9/11/2026", "caption": "1 Bedroom, 1 Bathroom"}],
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            capture_path = Path(directory) / "capture.json"
            output_db = Path(directory) / "listings.db"
            capture_path.write_text(json.dumps(capture), encoding="utf-8")
            result = import_capture(capture_path, output_db)
            self.assertEqual(result["listings"], 1)
            self.assertEqual(result["new"], 1)
            conn = sqlite3.connect(output_db)
            row = conn.execute(
                "SELECT source,source_id,address,unit_number,status FROM listings"
            ).fetchone()
            conn.close()
        self.assertEqual(row, ("securecafe", "sc-aalto57-06F",
                               "1065 2nd Ave", "06F", "active"))


if __name__ == "__main__":
    unittest.main()
