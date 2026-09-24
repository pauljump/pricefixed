import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "merges" / "merge_dof_unit_lot_classifications.py"
SPEC = importlib.util.spec_from_file_location("merge_dof_unit_lot_classifications", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DofUnitLotMergeTest(unittest.TestCase):
    def test_extracts_statement_date(self):
        url = "https://example.test/StatementSearch?bbl=1001&stmtDate=20251115&stmtType=SOA"
        self.assertEqual(MODULE.statement_date(url), "2025-11-15")

    def test_stable_ids_are_repeatable_and_namespaced(self):
        self.assertEqual(MODULE.stable_id("unit", "1", "2"), MODULE.stable_id("unit", "1", "2"))
        self.assertNotEqual(MODULE.stable_id("unit", "1", "2"), MODULE.stable_id("doc", "1", "2"))


if __name__ == "__main__":
    unittest.main()
