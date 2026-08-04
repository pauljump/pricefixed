import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.merges.audit_nyc_unit_text_markers import (
    load_completed,
    marker_where,
    query_count,
    text_fields,
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


if __name__ == "__main__":
    unittest.main()
