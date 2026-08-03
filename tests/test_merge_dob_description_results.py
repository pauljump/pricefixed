import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "merges" / "merge_dob_description_results.py"
SPEC = importlib.util.spec_from_file_location("merge_dob_description_results", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DobDescriptionMergeTest(unittest.TestCase):
    def test_stable_id_includes_namespace_and_label(self):
        self.assertEqual(MODULE.stable_id("unit", "1", "2A"), MODULE.stable_id("unit", "1", "2A"))
        self.assertNotEqual(MODULE.stable_id("unit", "1", "2A"), MODULE.stable_id("doc", "1", "2A"))


if __name__ == "__main__":
    unittest.main()
