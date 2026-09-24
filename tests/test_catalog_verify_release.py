import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pricefixed.catalog import init_catalog_db


class CatalogVerifyReleaseTests(unittest.TestCase):
    def _release(self, root):
        database = root / "catalog.db"
        connection = init_catalog_db(database)
        stamp = "2026-08-01T00:00:00Z"
        connection.execute("INSERT INTO sources VALUES (?,?,?,?,?)", ("hpd_violations", "public_record", "test", stamp, stamp))
        connection.execute("INSERT INTO units VALUES (?,?,?,?,?,?)", ("unit-1", "1000000001", "4B", "4B", stamp, stamp))
        connection.execute(
            "INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("obs-1", None, "hpd_violations", "ref", stamp, "violation", "4 Example St", "4B", None, None, None, None, "{}", "source_document"),
        )
        connection.execute(
            "INSERT INTO entity_matches VALUES (?,?,?,?,?,?,?,?)",
            ("obs-1", "unit", "unit-1", "resolved", 1.0, "test", "test", stamp),
        )
        connection.commit()
        connection.close()
        release = root / "release"
        repo = Path(__file__).resolve().parents[1]
        subprocess.run([sys.executable, "catalog_export.py", "--db", str(database), "--out", str(release)], check=True, cwd=repo)
        subprocess.run([sys.executable, "catalog_report.py", "--db", str(database), "--out", str(release / "quality-report.json")], check=True, cwd=repo)
        return release

    def test_verifies_consistent_release(self):
        with tempfile.TemporaryDirectory() as directory:
            release = self._release(Path(directory))
            result = subprocess.run(
                [sys.executable, "catalog_verify_release.py", str(release)],
                cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["release_units"], 1)

    def test_rejects_tampered_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            release = self._release(Path(directory))
            with (release / "units.csv").open("a", encoding="utf-8") as handle:
                handle.write("tampered\n")
            result = subprocess.run(
                [sys.executable, "catalog_verify_release.py", str(release)],
                cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("checksum mismatch: units.csv", result.stderr)
