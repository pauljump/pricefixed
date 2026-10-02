import unittest

from tools.merges.mine_condo_area_delta import choose_label, official_unit_label


class CondoAreaDeltaTest(unittest.TestCase):
    def test_explicit_official_unit_field_keeps_4f(self):
        self.assertEqual(official_unit_label("4F"), "4F")
        self.assertEqual(official_unit_label("STOR2"), "")

    def test_uses_unique_acris_label_for_residential_generic_unit(self):
        row = {
            "unit_bbl": "1008661015", "base_bbl": "1008660048", "unit_lot": "1015",
            "unit_designation": "UNIT", "room_desc": "STUDIO",
        }
        self.assertEqual(
            choose_label(row, ["3D", "3D"], set()),
            ("3D", "residential_geometry_plus_acris_label", ""),
        )

    def test_rejects_duplicate_designation_on_sibling_lot(self):
        row = {
            "unit_bbl": "1004271614", "base_bbl": "1004270200", "unit_lot": "1614",
            "unit_designation": "PH2", "room_desc": "",
        }
        self.assertEqual(
            choose_label(row, [], {("1004270200", "PH2")})[2],
            "duplicate_designation_in_condo",
        )

    def test_requires_acris_when_geometry_lot_disagrees(self):
        row = {
            "unit_bbl": "1001061204", "base_bbl": "1001060004", "unit_lot": "1203",
            "unit_designation": "2R", "room_desc": "",
        }
        self.assertEqual(choose_label(row, [], set())[2], "unit_lot_mismatch_without_acris_support")
        self.assertEqual(choose_label(row, ["2R"], set())[0], "2R")
