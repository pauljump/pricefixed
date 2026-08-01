import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pricefixed.catalog import init_catalog_db


class CatalogExportTests(unittest.TestCase):
    def test_exports_stable_payload_free_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "catalog.db"
            connection = init_catalog_db(database)
            connection.execute(
                "INSERT INTO sources VALUES (?,?,?,?,?)",
                ("example", "public_record", "test source", "2026-08-01T00:00:00Z", "2026-08-01T00:00:00Z"),
            )
            unit_id = "unit-example"
            observation_id = "observation-example"
            connection.execute(
                "INSERT INTO units VALUES (?,?,?,?,?,?)",
                (unit_id, "1000000001", "4B", "4B", "2026-08-01T00:00:00Z", "2026-08-01T00:00:00Z"),
            )
            connection.execute(
                "INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (observation_id, None, "example", "source-ref", "2026-08-01T00:00:00Z", "listing",
                 "4 Example St", "4B", 1, 1, 2500, "active", '{"private":"not exported"}', "source_document"),
            )
            connection.execute(
                "INSERT INTO entity_matches VALUES (?,?,?,?,?,?,?,?)",
                (observation_id, "unit", unit_id, "resolved", 1.0, "test", "test", "2026-08-01T00:00:00Z"),
            )
            connection.commit()
            connection.close()

            output = root / "release"
            subprocess.run(
                [sys.executable, "catalog_export.py", "--db", str(database), "--out", str(output)],
                check=True,
                cwd=Path(__file__).resolve().parents[1],
            )

            with (output / "unit_observations.csv").open(newline="") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(reader.fieldnames, [
                    "unit_id", "observation_id", "source", "source_ref", "observed_at",
                    "observation_kind", "address", "unit_label", "bedrooms", "bathrooms",
                    "price", "status", "evidence_grade", "resolution_confidence",
                    "resolution_method", "matched_at",
                ])
                rows = list(reader)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["unit_id"], unit_id)
            self.assertNotIn("raw_fields", rows[0])
            self.assertNotIn("private", (output / "unit_observations.csv").read_text())
            with (output / "units.csv").open(newline="") as handle:
                self.assertEqual(next(csv.reader(handle)), [
                    "unit_id", "bbl", "unit_label", "normalized_unit", "first_seen", "last_seen"
                ])
            with (output / "sources.csv").open(newline="") as handle:
                self.assertEqual(next(csv.reader(handle)), [
                    "source", "source_kind", "methodology", "first_seen", "last_seen"
                ])
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["format"], "pricefixed-catalog-v1")
            self.assertEqual(manifest["release_id"], "release")
            self.assertEqual(manifest["files"]["units.csv"]["rows"], 1)
            self.assertEqual(set(manifest["files"]), {"units.csv", "unit_observations.csv", "sources.csv"})
            digest = hashlib.sha256((output / "units.csv").read_bytes()).hexdigest()
            self.assertEqual(manifest["files"]["units.csv"]["sha256"], digest)

    def test_refuses_to_overwrite_a_nonempty_release_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "catalog.db"
            init_catalog_db(database).close()
            output = root / "release"
            output.mkdir()
            (output / "keep.txt").write_text("do not overwrite")
            result = subprocess.run(
                [sys.executable, "catalog_export.py", "--db", str(database), "--out", str(output)],
                cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must be new or empty", result.stderr)
            self.assertEqual((output / "keep.txt").read_text(), "do not overwrite")


if __name__ == "__main__":
    unittest.main()
