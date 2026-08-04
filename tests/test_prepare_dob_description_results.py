import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "local_model" / "prepare_dob_description_results.py"
SPEC = importlib.util.spec_from_file_location("prepare_dob_description_results", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DobCandidateBoundaryTest(unittest.TestCase):
    def test_accepts_standalone_candidate(self):
        self.assertTrue(MODULE.candidate_is_standalone("3L", "NO WORK IN APARTMENT 3L, ONLY CAP PIPE"))

    def test_accepts_labels_reproduced_from_clear_compounds(self):
        self.assertTrue(MODULE.candidate_is_standalone("14J", "APARTMENT 14J/14K"))
        self.assertTrue(MODULE.candidate_is_standalone("14K", "APARTMENT 14J/14K"))
        self.assertTrue(MODULE.candidate_is_standalone("12B", "APARTMENT 12B/C"))
        self.assertTrue(MODULE.candidate_is_standalone("12C", "APARTMENT 12B/C"))

    def test_rejects_candidates_the_parser_cannot_reproduce(self):
        self.assertFalse(MODULE.candidate_is_standalone("B701-B702", "APARTMENT B701-B702-B703"))
        self.assertFalse(MODULE.candidate_is_standalone("2", "WORK IN APT 2 R ONLY"))

    def test_accepts_electrical_detail_specific_candidates_with_source_parser(self):
        from tools.merges.mine_dob_electrical_detail_units import extract_electrical_detail_labels

        self.assertTrue(
            MODULE.candidate_is_standalone(
                "G", "16th Floor, Apartment G", extract_electrical_detail_labels
            )
        )
        self.assertTrue(
            MODULE.candidate_is_standalone(
                "4M", "General wiring in Unit 4M", extract_electrical_detail_labels
            )
        )

    def test_transport_errors_do_not_count_as_terminal_results(self):
        rows = [
            {"id": "retry", "status": "error"},
            {"id": "done", "status": "ok", "parsed": {"unit_labels": []}},
            {"id": "retry", "status": "ok", "parsed": {"unit_labels": []}},
            {"id": "bad-json", "status": "invalid_json"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.jsonl"
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            results = MODULE.load_terminal_results(path)
        self.assertEqual(set(results), {"retry", "done", "bad-json"})
        self.assertEqual(results["retry"]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
