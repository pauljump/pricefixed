import importlib.util
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "local_model" / "run_qwen_extraction.py"
SPEC = importlib.util.spec_from_file_location("run_qwen_extraction", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class LocalQwenRunnerTest(unittest.TestCase):
    def test_cache_ignores_filing_url_but_not_source_text(self):
        first = {"source_type": "dob", "target_address": "1 MAIN ST", "text": "APT 2A", "source_url": "a"}
        duplicate = dict(first, source_url="b")
        different = dict(first, text="APT 2B")
        different_candidates = dict(first, candidate_labels=["2A"])
        self.assertEqual(MODULE.cache_key(first), MODULE.cache_key(duplicate))
        self.assertNotEqual(MODULE.cache_key(first), MODULE.cache_key(different))
        self.assertNotEqual(MODULE.cache_key(first), MODULE.cache_key(different_candidates))

    def test_resume_retries_errors_but_keeps_terminal_results(self):
        records = {
            "ok": {"id": "ok", "source_type": "dob", "target_address": "1 MAIN ST", "text": "APT 2A"},
            "bad-json": {"id": "bad-json", "source_type": "dob", "target_address": "2 MAIN ST", "text": "APT 3A"},
            "error": {"id": "error", "source_type": "dob", "target_address": "3 MAIN ST", "text": "APT 4A"},
        }
        rows = [
            {"id": "ok", "status": "ok", "parsed": {"unit_labels": []},
             "input_fingerprint": MODULE.input_fingerprint(records["ok"])},
            {"id": "bad-json", "status": "invalid_json",
             "input_fingerprint": MODULE.input_fingerprint(records["bad-json"])},
            {"id": "error", "status": "error", "error": "connection refused"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results.jsonl"
            output.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            completed, cached = MODULE.load_existing_results(output, records)
        self.assertEqual(completed, {"ok", "bad-json"})
        self.assertIn(MODULE.cache_key(records["ok"]), cached)
        self.assertNotIn("error", completed)

    def test_resume_retries_unfingerprinted_legacy_results(self):
        record = {"id": "legacy", "text": "APT 2A"}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results.jsonl"
            output.write_text(
                json.dumps({"id": "legacy", "status": "ok", "parsed": {}}) + "\n",
                encoding="utf-8",
            )
            completed, cached = MODULE.load_existing_results(output, {"legacy": record})
        self.assertEqual(completed, set())
        self.assertEqual(cached, {})

    def test_resume_rejects_a_result_for_changed_model_inputs(self):
        original = {
            "id": "same-id", "source_type": "dob", "target_address": "1 MAIN ST",
            "text": "APT 2A", "candidate_labels": ["2A"],
        }
        changed = dict(original, candidate_labels=["2B"])
        row = {
            "id": "same-id", "status": "ok", "parsed": {"unit_labels": []},
            "input_fingerprint": MODULE.input_fingerprint(original),
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results.jsonl"
            output.write_text(json.dumps(row) + "\n", encoding="utf-8")
            completed, cached = MODULE.load_existing_results(output, {"same-id": changed})
        self.assertEqual(completed, set())
        self.assertEqual(cached, {})

    def test_retry_succeeds_without_consuming_a_failed_attempt(self):
        calls = []

        def flaky():
            calls.append(True)
            if len(calls) < 3:
                raise MODULE.URLError("offline")
            return "raw", {"unit_labels": []}

        self.assertEqual(MODULE.call_with_retries(flaky, 3, 0)[0], "raw")
        self.assertEqual(len(calls), 3)

    def test_malformed_batch_stops_after_two_attempts(self):
        calls = []

        def malformed():
            calls.append(True)
            raise KeyError("incomplete batch")

        with self.assertRaises(RuntimeError):
            MODULE.call_with_retries(malformed, 5, 0)
        self.assertEqual(len(calls), 2)

    def test_malformed_batch_splits_to_single_records(self):
        records = [
            {"id": "a", "text": "APT 2A", "candidate_labels": ["2A"]},
            {"id": "b", "text": "APT 3B", "candidate_labels": ["3B"]},
        ]
        args = Namespace(
            base_url="local", model="qwen", max_tokens=1024, temperature=0.2,
            timeout=10, retry_attempts=5, retry_delay=0,
        )
        parsed = {
            "building_address": None, "unit_labels": [], "residential_count": None,
            "confidence": "high", "notes": "",
        }
        with patch.object(MODULE, "call_model_batch", side_effect=KeyError("bad batch")), \
                patch.object(MODULE, "call_model", return_value=("{}", parsed)) as singles:
            results = MODULE.extract_batch_with_fallback(args, records)
        self.assertEqual(set(results), {MODULE.cache_key(record) for record in records})
        self.assertEqual(singles.call_count, 2)

    def test_parse_batch_requires_every_expected_id_once(self):
        text = json.dumps([
            {"id": "a", "unit_labels": [{"label": "2A", "evidence": "APT 2A"}], "confidence": "high"},
            {"id": "b", "unit_labels": [], "confidence": "low"},
        ])
        parsed = MODULE.parse_batch_json(text, ["a", "b"])
        self.assertEqual(set(parsed), {"a", "b"})
        self.assertIsNone(MODULE.parse_batch_json(text, ["a", "missing"]))

    def test_standardize_batch_item_uses_common_result_schema(self):
        item = {"id": "a", "unit_labels": [{"label": "2A", "evidence": "APT 2A"}], "confidence": "high"}
        parsed = MODULE.standardize_batch_item(item, {"target_address": "1 MAIN ST"})
        self.assertEqual(parsed["building_address"], "1 MAIN ST")
        self.assertEqual(parsed["unit_labels"][0]["page"], None)


if __name__ == "__main__":
    unittest.main()
