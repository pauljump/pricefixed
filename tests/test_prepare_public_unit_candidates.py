import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "merges" / "prepare_public_unit_candidates.py"
SPEC = importlib.util.spec_from_file_location("prepare_public_unit_candidates", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class UsableDwellingLabelTest(unittest.TestCase):
    def test_accepts_compact_apartment_identifiers(self):
        for label, expected in (("6D", "6D"), ("#204", "204"), ("A11", "A11"),
                                ("PH", "PH"), ("B701", "B701"), ("001", "1")):
            with self.subTest(label=label):
                self.assertEqual(MODULE.usable_dwelling_label("hpd_violations", label), expected)

    def test_rejects_location_and_non_dwelling_labels(self):
        for label in ("NONE", "2ND FLOOR", "2FL", "FIRST", "GROUND STORE", "ATTIC",
                      "PRIVATE HOUSE", "COMMERCIAL STORE & B", "OSP", "0"):
            with self.subTest(label=label):
                self.assertIsNone(MODULE.usable_dwelling_label("evictions", label))

    def test_rejects_collapsed_multi_unit_labels(self):
        for label in ("5D/6D", "002, 003", "1S & 1T"):
            with self.subTest(label=label):
                self.assertIsNone(MODULE.usable_dwelling_label("dob_jobs", label))

    def test_rejects_free_text_and_keeps_raw_hpd_evidence_outside_catalog(self):
        self.assertIsNone(MODULE.usable_dwelling_label("hpd_problems", "APARTMENT"))
        self.assertIsNone(MODULE.usable_dwelling_label("hpd_problems", "2ND FLO"))
        self.assertIsNone(MODULE.usable_dwelling_label("hpd_problems", "1 REAR"))


if __name__ == "__main__":
    unittest.main()
