import unittest

from tools.merges.mine_dob_target_descriptions import collect


class MineDobTargetDescriptionsTest(unittest.TestCase):
    def test_requires_exact_address_and_emits_explicit_labels(self):
        targets = [{
            "property": "Stuyvesant Town",
            "address": "620 EAST 20 STREET",
            "resolved_bbl": "1009720001",
        }]

        def fetch(bbl):
            self.assertEqual(bbl, "1009720001")
            return ([
                {
                    "job_filing_number": "M00816454-I1", "bbl": bbl,
                    "house_no": "620", "street_name": "EAST 20 STREET",
                    "filing_date": "2023-02-01", "job_description":
                        "General construction for interior renovation of Apartment 10C on the 11th floor.",
                },
                {
                    "job_filing_number": "MISMATCH", "bbl": bbl,
                    "house_no": "624", "street_name": "EAST 20 STREET",
                    "filing_date": "2023-02-01", "job_description": "Apartment 3D.",
                },
            ], "https://example.test/dob")

        rows = collect(targets, fetch=fetch)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["unit_label"], "10C")
        self.assertEqual(rows[0]["status"], "explicit_candidate")
        self.assertEqual(rows[0]["source_ref"], "M00816454-I1")

    def test_retains_ambiguous_marker_rows_without_making_a_unit(self):
        targets = [{
            "property": "Stuyvesant Town",
            "address": "620 EAST 20 STREET",
            "resolved_bbl": "1009720001",
        }]

        rows = collect(targets, fetch=lambda bbl: ([{
            "job_filing_number": "M-AMB", "bbl": bbl,
            "house_no": "620", "street_name": "EAST 20 STREET",
            "filing_date": "2023-02-01", "job_description": "Apartment renovations as shown on plans.",
        }], "https://example.test/dob"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["unit_label"], "")
        self.assertEqual(rows[0]["status"], "ambiguous_description")


if __name__ == "__main__":
    unittest.main()
