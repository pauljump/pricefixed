import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.merges.audit_nyc_unit_text_markers import (
    load_decisions,
    load_completed,
    load_results,
    marker_where,
    query_count,
    text_fields,
    unreviewed_nonzero,
)


class AuditNycUnitTextMarkersTest(unittest.TestCase):
    def setUp(self):
        self.dataset = {
            "id": "abcd-1234", "name": "Homes",
            "fields": ["bbl", "job_description", "worker_count"],
            "types": {"bbl": "Text", "job_description": "Text", "worker_count": "Number"},
        }

    def test_keeps_only_text_description_fields(self):
        self.assertEqual(text_fields(self.dataset), ["job_description"])
        clause = marker_where(self.dataset, text_fields(self.dataset))
        self.assertIn("bbl is not null", clause)
        self.assertIn("upper(job_description)", clause)
        self.assertNotIn("like '%APT%'", clause)

    @patch("tools.merges.audit_nyc_unit_text_markers.urlopen")
    def test_queries_dataset_count(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = b'[{"rows":"12"}]'
        self.assertEqual(query_count(self.dataset, ["job_description"]), 12)
        self.assertIn("/abcd-1234.json", urlopen.call_args.args[0].full_url)

    def test_resumes_completed_dataset_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.jsonl"
            path.write_text(json.dumps({"dataset": "abcd-1234"}) + "\n")
            self.assertEqual(load_completed(path), {"abcd-1234"})

    def test_requires_decisions_for_every_nonzero_result(self):
        results = [
            {"dataset": "reviewed", "status": "ok", "rows": 2},
            {"dataset": "missing", "status": "ok", "rows": 1},
            {"dataset": "zero", "status": "ok", "rows": 0},
            {"dataset": "failed", "status": "error"},
        ]
        self.assertEqual(
            unreviewed_nonzero(results, {"reviewed": {"decision": "collect"}}),
            ["missing"],
        )

    def test_loads_and_validates_decision_register(self):
        with tempfile.TemporaryDirectory() as directory:
            decisions_path = Path(directory) / "decisions.json"
            decisions_path.write_text(json.dumps({
                "datasets": {
                    "abcd-1234": {"decision": "exclude", "handling": "not a home"}
                }
            }))
            self.assertIn("abcd-1234", load_decisions(decisions_path))

            results_path = Path(directory) / "results.jsonl"
            results_path.write_text(json.dumps({"dataset": "abcd-1234"}) + "\n")
            self.assertEqual(load_results(results_path)[0]["dataset"], "abcd-1234")


if __name__ == "__main__":
    unittest.main()
