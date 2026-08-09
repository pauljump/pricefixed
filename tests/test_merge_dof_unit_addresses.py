import unittest

from tools.merges.merge_dof_unit_addresses import normalize_unit, row_reasons, statement_date


class MergeDofUnitAddressesTest(unittest.TestCase):
    def test_normalizes_statement_date(self):
        self.assertEqual(statement_date("20251115"), "2025-11-15")
        self.assertEqual(statement_date("unknown"), "unknown")

    def test_requires_existing_official_identity_and_matching_designation(self):
        official = {"3072791003": "1"}
        units = {("3072791003", normalize_unit("1"))}
        row = {
            "unit_lot_bbl": "3072791003",
            "unit_designation": "1",
            "official_unit_designation": "1",
            "address": "501 SURF AVE. APT 1",
            "source_url": "https://a836-edms.nyc.gov/example",
            "statement_date": "20251115",
            "validation_status": "accepted",
        }
        self.assertEqual(row_reasons(row, official, units), [])
        row["unit_designation"] = "2"
        row["official_unit_designation"] = "2"
        self.assertEqual(
            row_reasons(row, official, units),
            ["unit_designation_mismatch", "unit_identity_not_in_catalog"],
        )

    def test_rejects_address_only_candidate(self):
        row = {
            "unit_lot_bbl": "3072791003",
            "unit_designation": "1",
            "official_unit_designation": "1",
            "address": "501 SURF AVE. APT 1",
            "source_url": "https://a836-edms.nyc.gov/example",
            "validation_status": "accepted",
        }
        reasons = row_reasons(row, {}, set())
        self.assertIn("not_in_official_unit_lots", reasons)
        self.assertIn("unit_identity_not_in_catalog", reasons)


if __name__ == "__main__":
    unittest.main()
