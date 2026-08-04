import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pricefixed.catalog import init_catalog_db


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "merges" / "revalidate_description_observations.py"


class DescriptionObservationRevalidationTest(unittest.TestCase):
    def test_removes_only_unsupported_observation_and_orphan_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "catalog.db"
            catalog = init_catalog_db(database)
            catalog.execute(
                "INSERT INTO sources VALUES (?,?,?,?,?)",
                ("test_descriptions", "public_record", "test", "2026-08-04", "2026-08-04"),
            )
            catalog.execute(
                "INSERT INTO sources VALUES (?,?,?,?,?)",
                ("other_source", "public_record", "test", "2026-08-04", "2026-08-04"),
            )
            for suffix, label in (
                ("bad", "6AINSTALL"), ("shared", "8DEXISTING"), ("good", "7B")
            ):
                unit_id = f"unit-{suffix}"
                document_id = f"doc-{suffix}"
                observation_id = f"obs-{suffix}"
                catalog.execute(
                    "INSERT INTO source_documents VALUES (?,?,?,?,?,?)",
                    (document_id, "test_descriptions", suffix, "2026-08-04", "{}", "test"),
                )
                catalog.execute(
                    "INSERT INTO buildings(bbl,source,first_seen,last_seen) VALUES (?,?,?,?) "
                    "ON CONFLICT DO NOTHING",
                    ("1000000001", "test_descriptions", "2026-08-04", "2026-08-04"),
                )
                catalog.execute(
                    "INSERT INTO units VALUES (?,?,?,?,?,?)",
                    (unit_id, "1000000001", label, label, "2026-08-04", "2026-08-04"),
                )
                raw = json.dumps({"upstream_source_ref": suffix})
                catalog.execute(
                    "INSERT INTO observations "
                    "(observation_id,document_id,source,source_ref,observed_at,observation_kind,"
                    "unit_label,raw_fields,evidence_grade) VALUES (?,?,?,?,?,?,?,?,?)",
                    (observation_id, document_id, "test_descriptions", suffix, "2026-08-04",
                     "official_unit_label", label, raw, "source_document"),
                )
                catalog.execute(
                    "INSERT INTO entity_matches VALUES (?,?,?,?,?,?,?,?)",
                    (observation_id, "unit", unit_id, "resolved", 1.0, "test", "test", "2026-08-04"),
                )
            catalog.execute(
                "INSERT INTO source_documents VALUES (?,?,?,?,?,?)",
                ("doc-shared-support", "other_source", "shared", "2026-08-04", "{}", "test"),
            )
            catalog.execute(
                "INSERT INTO observations "
                "(observation_id,document_id,source,source_ref,observed_at,observation_kind,"
                "unit_label,raw_fields,evidence_grade) VALUES (?,?,?,?,?,?,?,?,?)",
                ("obs-shared-support", "doc-shared-support", "other_source", "shared",
                 "2026-08-04", "official_unit_label", "8DEXISTING", "{}", "source_document"),
            )
            catalog.execute(
                "INSERT INTO entity_matches VALUES (?,?,?,?,?,?,?,?)",
                ("obs-shared-support", "unit", "unit-shared", "resolved", 1.0,
                 "test", "test", "2026-08-04"),
            )
            catalog.commit()
            catalog.close()
            packets = root / "packets.jsonl"
            packets.write_text("".join(
                json.dumps({"id": "packet-" + ref, "text": text}) + "\n"
                for ref, text in (
                    ("bad", "APT 6AINSTALL"),
                    ("shared", "APT 8DEXISTING"),
                    ("good", "APT 7B"),
                )
            ))
            summary = root / "summary.json"
            completed = subprocess.run([
                sys.executable, str(SCRIPT), "--packets", str(packets),
                "--catalog-db", str(database), "--source", "test_descriptions",
                "--summary", str(summary), "--packet-id-prefix", "packet-", "--apply",
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(summary.read_text())
            self.assertEqual(result["invalid_observations"], 2)
            self.assertEqual(result["orphan_units_removed"], 1)
            catalog = sqlite3.connect(database)
            self.assertEqual(
                catalog.execute("SELECT unit_label FROM units ORDER BY unit_label").fetchall(),
                [("7B",), ("8DEXISTING",)],
            )
            self.assertEqual(
                catalog.execute("SELECT observation_id FROM observations ORDER BY observation_id").fetchall(),
                [("obs-good",), ("obs-shared-support",)],
            )
            self.assertEqual(
                catalog.execute("SELECT document_id FROM source_documents ORDER BY document_id").fetchall(),
                [("doc-good",), ("doc-shared-support",)],
            )
            catalog.close()


if __name__ == "__main__":
    unittest.main()
