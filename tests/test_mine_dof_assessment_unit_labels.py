import unittest

from tools.merges.mine_dof_assessment_unit_labels import usable_label


class DofAssessmentUnitLabelTest(unittest.TestCase):
    def test_keeps_compact_residential_labels(self):
        self.assertEqual(usable_label("4-A"), "4A")
        self.assertEqual(usable_label("PH2"), "PH2")

    def test_rejects_sentinels_and_nonunit_spaces(self):
        self.assertEqual(usable_label("`"), "")
        self.assertEqual(usable_label("GARAGE 2"), "")
        self.assertEqual(usable_label("CELLAR"), "")
