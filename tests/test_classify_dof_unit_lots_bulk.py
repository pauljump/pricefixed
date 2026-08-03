import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "merges" / "classify_dof_unit_lots_bulk.py"
SPEC = importlib.util.spec_from_file_location("classify_dof_unit_lots_bulk", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DofBulkClassificationTest(unittest.TestCase):
    def test_classifies_residential_and_nonresidential_tax_classes(self):
        self.assertEqual(MODULE.classification("2"), "residential_tax_class")
        self.assertEqual(MODULE.classification("2A"), "residential_tax_class")
        self.assertEqual(MODULE.classification("4"), "nonresidential_tax_class")
        self.assertEqual(MODULE.classification(""), "tax_class_not_found")

    def test_builds_assessment_address_without_owner_data(self):
        row = {"housenum_lo": "12", "housenum_hi": "14", "street_name": "MAIN STREET"}
        self.assertEqual(MODULE.assessment_address(row), "12-14 MAIN STREET")


if __name__ == "__main__":
    unittest.main()
