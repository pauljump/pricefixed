import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tools.merges.build_complex_unit_evidence import build_evidence


class ComplexUnitEvidenceTest(unittest.TestCase):
    def test_keeps_exact_address_and_shared_bbl_evidence_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            inventory = directory / "inventory.json"
            catalog = directory / "catalog.db"
            packets = directory / "packets.jsonl"
            inventory.write_text(json.dumps({
                "rows": [
                    {
                        "property": "Peter Cooper Village",
                        "normalized_address": "3 PETER COOPER RD",
                        "address": "3 PETER COOPER ROAD",
                        "resolved_bbl": "1009780001",
                        "listing_unit_labels": ["10A"],
                        "exact_premise_unit_labels": [],
                    },
                    {
                        "property": "Peter Cooper Village",
                        "normalized_address": "5 PETER COOPER RD",
                        "address": "5 PETER COOPER ROAD",
                        "resolved_bbl": "1009780001",
                        "listing_unit_labels": [],
                        "exact_premise_unit_labels": [],
                    },
                ]
            }), encoding="utf-8")
            connection = sqlite3.connect(catalog)
            connection.execute("CREATE TABLE units (bbl TEXT, unit_label TEXT)")
            connection.execute("INSERT INTO units VALUES (?,?)", ("1009780001", "11H"))
            connection.commit()
            connection.close()
            packets.write_text(
                json.dumps({
                    "source_type": "dob_job_description", "target_address": "3 PETER COOPER ROAD",
                    "bbl": "1009780001", "text": "Apartment 10 H.",
                }) + "\n" + json.dumps({
                    "source_type": "dob_job_description", "target_address": "9 PETER COOPER ROAD",
                    "bbl": "1009780001", "text": "Apartment 11 H.",
                }) + "\n",
                encoding="utf-8",
            )
            report = build_evidence(inventory, catalog, [packets])

        rows = {row["normalized_address"]: row for row in report["rows"]}
        self.assertEqual(rows["3 PETER COOPER RD"]["direct_address_unit_labels"], ["10A", "10H"])
        self.assertEqual(rows["3 PETER COOPER RD"]["packet_exact_unit_labels"], ["10H"])
        self.assertEqual(rows["3 PETER COOPER RD"]["packet_exact_unit_count"], 1)
        self.assertEqual(
            report["properties"][0]["packet_exact_address_unit_labels"], ["10H"]
        )
        self.assertEqual(report["properties"][0]["packet_shared_bbl_unit_labels"], ["11H"])
        self.assertEqual(report["properties"][0]["catalog_bbl_unit_labels"], ["11H"])


if __name__ == "__main__":
    unittest.main()
