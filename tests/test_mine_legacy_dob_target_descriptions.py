import unittest

from tools.merges.mine_legacy_dob_target_descriptions import collect


class MineLegacyDobTargetDescriptionsTest(unittest.TestCase):
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
                    "job_s1_no": "3212114", "bbl": bbl,
                    "house__": "620", "street_name": "EAST 20 STREET",
                    "latest_action_date": "08/11/2020", "job_description":
                        "CONSTRUCT NEW INTERIOR PARTITIONS IN APARTMENT 10C.",
                },
                {
                    "job_s1_no": "MISMATCH", "bbl": bbl,
                    "house__": "624", "street_name": "EAST 20 STREET",
                    "latest_action_date": "08/11/2020", "job_description":
                        "CONSTRUCT NEW INTERIOR PARTITIONS IN APARTMENT 3D.",
                },
            ], "https://example.test/legacy-dob")

        rows = collect(targets, fetch=fetch)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["unit_label"], "10C")
        self.assertEqual(rows[0]["status"], "explicit_candidate")
        self.assertEqual(rows[0]["source_ref"], "3212114")

    def test_keeps_targets_with_no_exact_rows_visible(self):
        targets = [{
            "property": "Stuyvesant Town",
            "address": "620 EAST 20 STREET",
            "resolved_bbl": "1009720001",
        }]
        rows = collect(
            targets,
            fetch=lambda bbl: ([], "https://example.test/legacy-dob"),
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "no_exact_source_rows")
        self.assertEqual(rows[0]["unit_label"], "")

    def test_retains_ambiguous_exact_source_rows(self):
        targets = [{
            "property": "Stuyvesant Town",
            "address": "620 EAST 20 STREET",
            "resolved_bbl": "1009720001",
        }]
        rows = collect(targets, fetch=lambda bbl: ([{
            "job_s1_no": "M-AMB", "bbl": bbl,
            "house__": "620", "street_name": "EAST 20 STREET",
            "latest_action_date": "08/11/2020",
            "job_description": "INTERIOR RENOVATION AS PER PLANS.",
        }], "https://example.test/legacy-dob"))
        self.assertEqual(rows[0]["status"], "ambiguous_description")
        self.assertEqual(rows[0]["evidence"], "INTERIOR RENOVATION AS PER PLANS.")


if __name__ == "__main__":
    unittest.main()
