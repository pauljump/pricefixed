import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.merges.mine_acris_gap_targets import query_target, target_key


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps([{
            "lot": "0001", "unit": "5D", "document_id": "202600000001",
            "good_through_date": "2026-08-08",
        }]).encode("utf-8")


class MineAcrisGapTargetsTest(unittest.TestCase):
    def test_accepts_complex_resolved_bbl_and_retains_exact_target(self):
        target = {
            "property": "Peter Cooper Village",
            "address": "342 1 AVENUE",
            "normalized_address": "342 1 AVE",
            "resolved_bbl": "1009780001",
        }
        with patch("tools.merges.mine_acris_gap_targets.urlopen", return_value=_Response()):
            rows = query_target(target)
        self.assertEqual(rows[0]["bbl"], "1009780001")
        self.assertEqual(rows[0]["property"], "Peter Cooper Village")
        self.assertEqual(rows[0]["unit_label"], "5D")
        self.assertEqual(rows[0]["status"], "unit_row")

    def test_checkpoint_key_includes_address_for_shared_bbl(self):
        first = {"bbl": "1009780001", "address": "342 1 AVE"}
        second = {"bbl": "1009780001", "address": "348 1 AVE"}
        self.assertNotEqual(target_key(first), target_key(second))


if __name__ == "__main__":
    unittest.main()
