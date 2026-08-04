import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "merges" / "mine_legacy_dob_description_units.py"
SPEC = importlib.util.spec_from_file_location("mine_legacy_dob_description_units", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class LegacyDobDescriptionTest(unittest.TestCase):
    def test_builds_bbl_from_legacy_borough_block_and_lot(self):
        self.assertEqual(MODULE.make_bbl("BROOKLYN", "123", "45"), "3001230045")
        self.assertEqual(MODULE.make_bbl("BROOKLYN", "00271", "00047"), "3002710047")

    def test_rejects_out_of_range_legacy_parcel_numbers(self):
        self.assertEqual(MODULE.make_bbl("BROOKLYN", "123456", "47"), "")
        self.assertEqual(MODULE.make_bbl("BROOKLYN", "271", "10000"), "")

    def test_only_extracts_explicit_residential_unit_language(self):
        text = "REPLACE HVAC UNIT 4. RENOVATE APARTMENT #3B AND DWELLING UNIT 2A."
        self.assertEqual(MODULE.extract_explicit_unit_labels(text), ["3B", "2A"])


if __name__ == "__main__":
    unittest.main()
