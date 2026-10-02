import os
import tempfile
import unittest
from unittest.mock import patch

import acris_stage
from pricefixed.catalog import Catalog, init_catalog_db


class AcrisStageTest(unittest.TestCase):
    def test_stages_raw_rows_and_repeats_document_boundary_idempotently(self):
        rows = [
            {"document_id": "202600000002", "borough": "1", "unit": "1A"},
            {"document_id": "202600000001", "borough": "1", "unit": "1B"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            conn = acris_stage.init_stage_db(os.path.join(directory, "stage.db"))
            with patch("acris_stage.fetch_page", return_value=rows):
                first = acris_stage.stage_page(conn, 2)
                second = acris_stage.stage_page(conn, 2)
            self.assertEqual(first, {"rows": 2, "inserted": 2, "cursor": "202600000001"})
            self.assertEqual(second, {"rows": 2, "inserted": 0, "cursor": "202600000001"})
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM staged_acris_unit_legals").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT cursor_ref FROM stage_keysets").fetchone()[0], "202600000001")
            conn.close()

    def test_resolves_staged_row_only_after_catalog_commit(self):
        row = {
            "document_id": "202600000001", "borough": "1", "block": "42", "lot": "7",
            "street_number": "45", "street_name": "Wall Street", "unit": "8D",
            "property_type": "CONDO", "good_through_date": "2026-07-01",
        }
        with tempfile.TemporaryDirectory() as directory:
            stage_path = os.path.join(directory, "stage.db")
            stage = acris_stage.init_stage_db(stage_path)
            with patch("acris_stage.fetch_page", return_value=[row]):
                acris_stage.stage_page(stage, 1)
            stage.close()
            catalog = Catalog(init_catalog_db(os.path.join(directory, "catalog.db")))
            stats = catalog.import_staged_acris_unit_legals(stage_path, limit=1)
            self.assertEqual(stats["acris_stage_rows"], 1)
            self.assertEqual(stats["acris_stage_rows_remaining"], 0)
            self.assertEqual(catalog.conn.execute("SELECT COUNT(*) FROM units").fetchone()[0], 1)

    def test_document_prefix_uses_a_separate_cursor_namespace(self):
        rows = [
            {"document_id": "FT_000000000002", "borough": "1", "unit": "2A"},
            {"document_id": "FT_000000000001", "borough": "1", "unit": "1A"},
        ]
        calls = []

        def fetch(cursor, page_size, document_prefix=None):
            calls.append((cursor, page_size, document_prefix))
            return rows

        with tempfile.TemporaryDirectory() as directory:
            conn = acris_stage.init_stage_db(os.path.join(directory, "stage.db"))
            with patch("acris_stage.fetch_page", side_effect=fetch):
                first = acris_stage.stage_page(conn, 2, document_prefix="FT_")
                second = acris_stage.stage_page(conn, 2, document_prefix="FT_")
            self.assertEqual(first["inserted"], 2)
            self.assertEqual(second["inserted"], 0)
            self.assertEqual(calls, [(None, 2, "FT_"), ("FT_000000000001", 2, "FT_")])
            self.assertEqual(
                conn.execute("SELECT source,cursor_ref FROM stage_keysets").fetchall(),
                [("acris_unit_legals:prefix=FT_", "FT_000000000001")],
            )
            conn.close()


if __name__ == "__main__":
    unittest.main()
