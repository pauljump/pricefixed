import unittest

from tools.merges.mine_ecb_description_units import issue_date, make_bbl


class EcbDescriptionTest(unittest.TestCase):
    def test_builds_bbl_from_official_fields(self):
        self.assertEqual(make_bbl("3", "04126", "0060"), "3041260060")
        self.assertEqual(make_bbl("", "04126", "0060"), "")

    def test_normalizes_compact_issue_date(self):
        self.assertEqual(issue_date("20100203"), "2010-02-03")
        self.assertEqual(issue_date("bad"), "")
        self.assertEqual(issue_date("20101340"), "")
