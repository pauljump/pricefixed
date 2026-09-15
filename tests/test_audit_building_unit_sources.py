import json
import tempfile
import unittest
from pathlib import Path

from tools.merges.audit_building_unit_sources import audit_packets, expected_roster


class BuildingUnitAuditTest(unittest.TestCase):
    def test_reparses_stale_candidates_and_separates_address_scope(self):
        packets = [
            {
                "id": "exact-10h", "source_type": "dob_job_description",
                "source_ref": "M1", "target_address": "3 Peter Cooper Road",
                "bbl": "10097800001",
                "text": "Apartment 10 H on the 11 floor", "candidate_labels": ["10"],
            },
            {
                "id": "other-11h", "source_type": "dob_job_description",
                "source_ref": "M2", "target_address": "5 Peter Cooper Road",
                "bbl": "1009780001",
                "text": "Apartment 11 H on the 12 floor", "candidate_labels": ["11"],
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "packets.jsonl"
            path.write_text("\n".join(json.dumps(packet) for packet in packets) + "\n", encoding="utf-8")
            report = audit_packets([path], "1009780001", "3 PETER COOPER ROAD")
        self.assertIn("10H", report["exact_address_labels"])
        self.assertIn("11H", report["shared_bbl_labels_only"])
        self.assertEqual(report["parser_repairs"][0]["reparsed_labels"], ["10H"])
        self.assertEqual(report["malformed_bbls_repaired"][0]["normalized_bbl"], "1009780001")

    def test_known_roster_shape_is_120_units(self):
        self.assertEqual(len(expected_roster()), 120)
        self.assertEqual(expected_roster()[0], "01A")
        self.assertEqual(expected_roster()[-1], "0MH")

    def test_coerces_approved_permit_record(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "approved-permit-25000.json"
            path.write_text(
                '[{"job_filing_number":"M1","bbl":"1009780001",'
                '"house_no":"3","street_name":"PETER COOPER ROAD",'
                '"job_description":"Interior renovation of Apartment 7E."}]\n',
                encoding="utf-8",
            )
            report = audit_packets([path], "1009780001", "3 PETER COOPER ROAD")
        self.assertEqual(report["exact_address_labels"], ["07E"])

    def test_reads_line_oriented_approved_permit_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "approved-permit-25000.json"
            path.write_text(
                '[{"job_filing_number":"M1","bbl":"1009780001",'
                '"house_no":"3","street_name":"PETER COOPER ROAD",'
                '"job_description":"Apartment 7E."}\n'
                ',{"job_filing_number":"M2","bbl":"1009780001",'
                '"house_no":"3","street_name":"PETER COOPER ROAD",'
                '"job_description":"Apartment 10H."}]\n',
                encoding="utf-8",
            )
            report = audit_packets([path], "1009780001", "3 PETER COOPER ROAD")
        self.assertEqual(report["exact_address_labels"], ["07E", "10H"])


if __name__ == "__main__":
    unittest.main()
