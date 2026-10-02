import csv
import os
import tempfile
import unittest

from pricefixed.catalog import init_catalog_db
from tools.merges.import_unit_labels import import_labels


class ImportUnitLabelsTest(unittest.TestCase):
    def test_requires_exact_catalog_address_and_creates_addressable_link(self):
        with tempfile.TemporaryDirectory() as directory:
            conn = init_catalog_db(os.path.join(directory, "catalog.db"))
            conn.executemany(
                "INSERT INTO addresses (address_id,bbl,address,normalized,zipcode,source) VALUES (?,?,?,?,?,?)",
                [
                    ("addr-3", "1009780001", "3 PETER COOPER ROAD", "3 PETER COOPER RD", "10010", "nyc_pad"),
                    ("addr-4", "1009780001", "4 PETER COOPER ROAD", "4 PETER COOPER RD", "10010", "nyc_pad"),
                ],
            )
            result = import_labels(conn, [
                {
                    "address": "3 Peter Cooper Road", "bbl": "1009780001", "unit_label": "5D",
                    "source_ref": "dob-co-1", "source_url": "https://example.test/co/1", "observed_at": "2026-08-08",
                },
                {
                    "address": "", "bbl": "1009780001", "unit_label": "6D",
                    "source_ref": "dob-co-2", "source_url": "https://example.test/co/2", "observed_at": "2026-08-08",
                },
                {
                    "address": "9 Peter Cooper Road", "bbl": "1009780001", "unit_label": "7D",
                    "source_ref": "dob-co-3", "source_url": "https://example.test/co/3", "observed_at": "2026-08-08",
                },
                {
                    "address": "3 Peter Cooper Road", "bbl": "1009780001", "unit_label": "PUBLIC HALL",
                    "source_ref": "dob-co-4", "source_url": "https://example.test/co/4", "observed_at": "2026-08-08",
                },
            ])
            self.assertEqual(len(result["imported"]), 1)
            self.assertEqual(
                sorted(row["rejection_reason"] for row in result["rejected"]),
                ["address_not_in_catalog_bbl", "missing_or_malformed_required_field", "non_dwelling_label"],
            )
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM units").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM premises").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM addressable_units").fetchone()[0], 1)
            observation = conn.execute(
                "SELECT address,unit_label FROM observations WHERE source='dob_occupancy_document_labels'"
            ).fetchone()
            self.assertEqual(tuple(observation), ("3 PETER COOPER ROAD", "5D"))

    def test_multiple_labels_from_one_document_remain_distinct_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            conn = init_catalog_db(os.path.join(directory, "catalog.db"))
            conn.execute(
                "INSERT INTO addresses (address_id,bbl,address,normalized,zipcode,source) VALUES (?,?,?,?,?,?)",
                ("addr-3", "1009780001", "3 PETER COOPER ROAD", "3 PETER COOPER RD", "10010", "nyc_pad"),
            )
            rows = [{
                "address": "3 PETER COOPER ROAD", "bbl": "1009780001", "unit_label": label,
                "source_ref": "dob-co-shared", "source_url": "https://example.test/co/shared",
                "observed_at": "2026-08-08",
            } for label in ("5D", "6D")]
            result = import_labels(conn, rows)
            self.assertEqual(len(result["imported"]), 2)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM observations WHERE source='dob_occupancy_document_labels'"
            ).fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM source_documents").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM addressable_units").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
