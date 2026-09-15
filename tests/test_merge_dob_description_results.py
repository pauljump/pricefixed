import importlib.util
import csv
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pricefixed.catalog.core import init_catalog_db


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "merges" / "merge_dob_description_results.py"
SPEC = importlib.util.spec_from_file_location("merge_dob_description_results", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DobDescriptionMergeTest(unittest.TestCase):
    def test_stable_id_includes_namespace_and_label(self):
        self.assertEqual(MODULE.stable_id("unit", "1", "2A"), MODULE.stable_id("unit", "1", "2A"))
        self.assertNotEqual(MODULE.stable_id("unit", "1", "2A"), MODULE.stable_id("doc", "1", "2A"))

    def test_apply_is_idempotent_after_a_partial_or_retried_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_path = root / "catalog.db"
            init_catalog_db(catalog_path).close()
            csv_path = root / "accepted.csv"
            with csv_path.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=(
                    "bbl", "address", "unit_label", "source_ref", "source_url",
                    "observed_at", "evidence", "confidence",
                ))
                writer.writeheader()
                writer.writerow({
                    "bbl": "1000000001", "address": "1 TEST ST", "unit_label": "2A",
                    "source_ref": "job-1", "source_url": "https://example.test/job-1",
                    "observed_at": "2026-08-03", "evidence": "APT 2A", "confidence": "high",
                })
            command = [
                sys.executable, str(SCRIPT), "--csv", str(csv_path),
                "--catalog-db", str(catalog_path), "--summary", str(root / "summary.json"),
                "--source", "test_description_units", "--apply",
            ]
            for _ in range(2):
                completed = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(completed.returncode, 0, completed.stderr)
            connection = sqlite3.connect(catalog_path)
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM observations WHERE source='test_description_units'"
            ).fetchone()[0], 1)
            self.assertEqual(json.loads((root / "summary.json").read_text())["catalog_writes"], 1)
            connection.close()


if __name__ == "__main__":
    unittest.main()
