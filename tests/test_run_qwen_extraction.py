import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "local_model" / "run_qwen_extraction.py"
SPEC = importlib.util.spec_from_file_location("run_qwen_extraction", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class LocalQwenRunnerTest(unittest.TestCase):
    def test_cache_ignores_filing_url_but_not_source_text(self):
        first = {"source_type": "dob", "target_address": "1 MAIN ST", "text": "APT 2A", "source_url": "a"}
        duplicate = dict(first, source_url="b")
        different = dict(first, text="APT 2B")
        self.assertEqual(MODULE.cache_key(first), MODULE.cache_key(duplicate))
        self.assertNotEqual(MODULE.cache_key(first), MODULE.cache_key(different))

    def test_resume_retries_errors_but_keeps_terminal_results(self):
        records = {
            "ok": {"id": "ok", "source_type": "dob", "target_address": "1 MAIN ST", "text": "APT 2A"},
            "bad-json": {"id": "bad-json", "source_type": "dob", "target_address": "2 MAIN ST", "text": "APT 3A"},
            "error": {"id": "error", "source_type": "dob", "target_address": "3 MAIN ST", "text": "APT 4A"},
        }
        rows = [
            {"id": "ok", "status": "ok", "parsed": {"unit_labels": []}},
            {"id": "bad-json", "status": "invalid_json"},
            {"id": "error", "status": "error", "error": "connection refused"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results.jsonl"
            output.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            completed, cached = MODULE.load_existing_results(output, records)
        self.assertEqual(completed, {"ok", "bad-json"})
        self.assertIn(MODULE.cache_key(records["ok"]), cached)
        self.assertNotIn("error", completed)

    def test_retry_succeeds_without_consuming_a_failed_attempt(self):
        calls = []

        def flaky():
            calls.append(True)
            if len(calls) < 3:
                raise MODULE.URLError("offline")
            return "raw", {"unit_labels": []}

        self.assertEqual(MODULE.call_with_retries(flaky, 3, 0)[0], "raw")
        self.assertEqual(len(calls), 3)


if __name__ == "__main__":
    unittest.main()
