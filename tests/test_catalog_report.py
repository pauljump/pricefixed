import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pricefixed.catalog import init_catalog_db


class CatalogReportTests(unittest.TestCase):
    def test_writes_release_quality_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "catalog.db"
            connection = init_catalog_db(database)
            connection.execute(
                "INSERT INTO sources VALUES (?,?,?,?,?)",
                ("hpd_violations", "public_record", "test source", "2026-08-01T00:00:00Z", "2026-08-01T00:00:00Z"),
            )
            connection.execute(
                "INSERT INTO buildings VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("1000000001", "MN", "4 Example St", "10001", 1, 1, "A1", "test", "2026-08-01", "2026-08-01"),
            )
            connection.execute(
                "INSERT INTO units VALUES (?,?,?,?,?,?)",
                ("unit-1", "1000000001", "4B", "4B", "2026-08-01", "2026-08-01"),
            )
            connection.execute(
                "INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("obs-1", None, "hpd_violations", "ref-1", "2026-08-01", "listing",
                 "4 Example St", "4B", 1, 1, 2500, "active", "{}", "source_document"),
            )
            connection.execute(
                "INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("obs-2", None, "hpd_violations", "ref-2", "2026-08-01", "listing",
                 "Bad Address", "4B", None, None, None, None, "{}", "legacy_snapshot"),
            )
            connection.execute(
                "INSERT INTO entity_matches VALUES (?,?,?,?,?,?,?,?)",
                ("obs-1", "unit", "unit-1", "resolved", 1.0, "test_match", "test", "2026-08-01"),
            )
            connection.execute(
                "INSERT INTO entity_matches VALUES (?,?,?,?,?,?,?,?)",
                ("obs-2", "unit", None, "unresolved", 0.0, "test_reject", "test", "2026-08-01"),
            )
            connection.execute(
                "INSERT INTO housing_capacity_slots VALUES (?,?,?,?)",
                ("slot-1", "1000000001", 1, "run-1"),
            )
            connection.commit()
            connection.close()

            output = root / "quality-report.json"
            subprocess.run(
                [
                    sys.executable, "catalog_report.py",
                    "--db", str(database),
                    "--out", str(output),
                    "--release-id", "2026-08-01",
                    "--commit", "abc123",
                ],
                check=True,
                cwd=Path(__file__).resolve().parents[1],
            )

            report = json.loads(output.read_text())
            self.assertEqual(report["format"], "pricefixed-quality-report-v1")
            self.assertEqual(report["release_id"], "2026-08-01")
            self.assertEqual(report["software_commit"], "abc123")
            self.assertEqual(report["counts"]["units"], 1)
            self.assertEqual(report["counts"]["resolved_unit_observations"], 1)
            self.assertEqual(report["counts"]["unresolved_unit_observations"], 1)
            self.assertEqual(report["counts"]["anonymous_capacity_slots"], 1)
            self.assertEqual(report["sources"], [{"value": "hpd_violations", "rows": 1}])
            self.assertEqual(
                report["evidence_grades"],
                [{"value": "source_document", "rows": 1}],
            )
            self.assertEqual(report["source_policy"]["policy_id"], "nyc-public-records-v1")
            self.assertEqual(report["warnings"], [])
            self.assertEqual({gap["name"] for gap in report["open_gaps"]}, {
                "anonymous_capacity_slots", "unresolved_unit_observations",
            })

    def test_missing_database_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    sys.executable, "catalog_report.py",
                    "--db", str(Path(directory) / "missing.db"),
                    "--out", str(Path(directory) / "report.json"),
                ],
                cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("catalog database not found", result.stderr)


if __name__ == "__main__":
    unittest.main()
