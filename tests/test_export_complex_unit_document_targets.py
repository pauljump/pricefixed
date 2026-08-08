import json
import tempfile
import unittest
from pathlib import Path

from tools.merges.export_complex_unit_document_targets import export_targets


class ComplexUnitDocumentTargetTest(unittest.TestCase):
    def test_exports_only_addresses_without_direct_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            evidence = directory / "evidence.json"
            output = directory / "targets.csv"
            evidence.write_text(json.dumps({
                "rows": [
                    {
                        "property": "Peter Cooper Village", "address": "3 PETER COOPER ROAD",
                        "normalized_address": "3 PETER COOPER RD", "resolved_bbl": "1009780001",
                        "listing_count": 2, "direct_address_unit_count": 1,
                    },
                    {
                        "property": "Peter Cooper Village", "address": "4 PETER COOPER ROAD",
                        "normalized_address": "4 PETER COOPER RD", "resolved_bbl": "1009780001",
                        "listing_count": 0, "direct_address_unit_count": 0,
                        "catalog_bbl_unit_count": 222, "inventory_origin": "anchor_bbl_catalog",
                    },
                ]
            }), encoding="utf-8")
            rows = export_targets(evidence, output)
            rendered = output.read_text(encoding="utf-8")
        self.assertEqual(len(rows), 1)
        self.assertIn("4 PETER COOPER ROAD", rendered)
        self.assertNotIn("3 PETER COOPER ROAD", rendered)
        self.assertIn("DOB occupancy document", rendered)


if __name__ == "__main__":
    unittest.main()
