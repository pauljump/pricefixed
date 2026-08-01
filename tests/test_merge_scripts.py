import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = [
    "tools/merges/extract_all.py",
    "tools/merges/build_hierarchy.py",
    "tools/merges/merge_known.py",
    "tools/merges/merge_single_family.py",
    "tools/merges/merge_tradable_tiebreak.py",
    "tools/merges/merge_condo_unit_lots.py",
    "tools/merges/run.py",
]


class MergeScriptCliTests(unittest.TestCase):
    def test_merge_scripts_expose_portable_cli_help(self):
        for script in SCRIPTS:
            result = subprocess.run(
                [sys.executable, script, "--help"], cwd=ROOT, text=True, capture_output=True
            )
            self.assertEqual(result.returncode, 0, msg=f"{script}: {result.stderr}")
            self.assertIn("usage:", result.stdout.lower())

    def test_merge_scripts_do_not_embed_workstation_paths(self):
        for script in SCRIPTS:
            text = (ROOT / script).read_text()
            self.assertNotIn("/Users/mini-home", text)
            self.assertNotIn("/Volumes/Backup Plus", text)


if __name__ == "__main__":
    unittest.main()
