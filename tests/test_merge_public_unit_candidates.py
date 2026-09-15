import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pricefixed.catalog import init_catalog_db


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "merges" / "merge_public_unit_candidates.py"


class PublicUnitCandidateMergeTest(unittest.TestCase):
    def test_apply_is_idempotent_across_committed_batches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_path = root / "catalog.db"
            init_catalog_db(catalog_path).close()
            mentions_path = root / "mentions.db"
            mentions = sqlite3.connect(mentions_path)
            mentions.execute(
                "CREATE TABLE unit_candidates ("
                "bbl TEXT, normalized_unit TEXT, unit_label TEXT, address TEXT, zipcode TEXT, "
                "source TEXT, source_ref TEXT, observed_at TEXT, dataset TEXT, source_url TEXT, "
                "exists_in_catalog INTEGER)"
            )
            mentions.execute(
                "INSERT INTO unit_candidates VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "1000000001", "2A", "2A", "1 TEST STREET", "10001",
                    "dob_jobs", "job-1", "2026-08-03", "test-data", "https://example.test/1", 0,
                ),
            )
            mentions.commit()
            mentions.close()

            command = [
                sys.executable, str(SCRIPT), "--mentions-db", str(mentions_path),
                "--catalog-db", str(catalog_path), "--batch-size", "1", "--apply",
            ]
            for _ in range(2):
                completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
                self.assertEqual(completed.returncode, 0, completed.stderr)

            catalog = sqlite3.connect(catalog_path)
            self.assertEqual(catalog.execute(
                "SELECT COUNT(*) FROM observations WHERE source='dob_now_jobs_compact'"
            ).fetchone()[0], 1)
            self.assertEqual(catalog.execute(
                "SELECT COUNT(*) FROM units WHERE bbl='1000000001' AND normalized_unit='2A'"
            ).fetchone()[0], 1)
            catalog.close()


if __name__ == "__main__":
    unittest.main()
