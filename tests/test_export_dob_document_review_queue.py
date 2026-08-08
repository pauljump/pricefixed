import csv
import tempfile
import unittest
from pathlib import Path

from tools.merges.export_dob_document_review_queue import export_queue


class DobDocumentReviewQueueTest(unittest.TestCase):
    def test_adds_exact_bis_link_and_keeps_review_fields_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            targets = directory / "targets.csv"
            output = directory / "review.csv"
            targets.write_text(
                "property,address,resolved_bbl\n"
                "Peter Cooper Village,342 1 AVENUE,1009780001\n",
                encoding="utf-8",
            )
            rows = export_queue(targets, output)
            with output.open(newline="", encoding="utf-8") as handle:
                rendered = next(csv.DictReader(handle))
        self.assertEqual(len(rows), 1)
        self.assertIn("houseno=342", rendered["bis_property_profile_url"])
        self.assertIn("street=1+AVENUE", rendered["bis_property_profile_url"])
        self.assertEqual(rendered["review_status"], "unreviewed")
        self.assertEqual(rendered["unit_label"], "")
        self.assertEqual(rendered["exact_address_match"], "")

    def test_keeps_unparseable_targets_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            targets = directory / "targets.csv"
            output = directory / "review.csv"
            targets.write_text("address,resolved_bbl\nUNKNOWN,1009780001\n", encoding="utf-8")
            rows = export_queue(targets, output)
        self.assertEqual(rows[0]["review_status"], "unparseable_address")
        self.assertEqual(rows[0]["bis_property_profile_url"], "")


if __name__ == "__main__":
    unittest.main()
