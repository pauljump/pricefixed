import importlib.util
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


if __name__ == "__main__":
    unittest.main()
