import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "tools" / "local_model" / "export_dob_description_packets.py"
)


class ExportDobDescriptionPacketsTest(unittest.TestCase):
    def test_normal_export_refreshes_stale_stored_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            descriptions = directory / "descriptions.db"
            catalog = directory / "catalog.db"
            output = directory / "packets.jsonl"
            with sqlite3.connect(descriptions) as connection:
                connection.executescript("""
                    CREATE TABLE progress (
                        source TEXT PRIMARY KEY, offset INTEGER, complete INTEGER, updated_at TEXT
                    );
                    INSERT INTO progress VALUES ('source', 1, 1, '2026-08-03');
                    CREATE TABLE descriptions (
                        job_filing_number TEXT PRIMARY KEY, bbl TEXT, address TEXT, zipcode TEXT,
                        description TEXT, filing_date TEXT, extracted_labels TEXT, status TEXT
                    );
                """)
                connection.execute(
                    "INSERT INTO descriptions VALUES (?,?,?,?,?,?,?,?)",
                    ("job-1", "1000000001", "1 TEST STREET", "", "Apartment 6AINSTALL",
                     "2026-08-03", json.dumps([]), "ambiguous_unit_word"),
                )
            with sqlite3.connect(catalog) as connection:
                connection.execute("CREATE TABLE units (bbl TEXT, normalized_unit TEXT)")
            subprocess.run([
                sys.executable, str(SCRIPT), "--descriptions-db", str(descriptions),
                "--catalog-db", str(catalog), "--output", str(output),
                "--progress-source", "source",
            ], check=True, capture_output=True, text=True)
            packet = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(packet["candidate_labels"], ["6A"])

    def test_parser_delta_exports_only_newly_recognized_missing_label(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            descriptions = directory / "descriptions.db"
            catalog = directory / "catalog.db"
            output = directory / "packets.jsonl"
            with sqlite3.connect(descriptions) as connection:
                connection.executescript("""
                    CREATE TABLE progress (
                        source TEXT PRIMARY KEY, offset INTEGER, complete INTEGER, updated_at TEXT
                    );
                    INSERT INTO progress VALUES ('source', 1, 1, '2026-08-03');
                    CREATE TABLE descriptions (
                        job_filing_number TEXT PRIMARY KEY, bbl TEXT, address TEXT, zipcode TEXT,
                        description TEXT, filing_date TEXT, extracted_labels TEXT, status TEXT
                    );
                """)
                connection.execute(
                    "INSERT INTO descriptions VALUES (?,?,?,?,?,?,?,?)",
                    ("job-1", "1000000001", "1 TEST STREET", "", "Apartment 12 C",
                     "2026-08-03", json.dumps(["12"]), "explicit_candidate"),
                )
            with sqlite3.connect(catalog) as connection:
                connection.execute(
                    "CREATE TABLE units (bbl TEXT, normalized_unit TEXT)"
                )
                connection.execute("INSERT INTO units VALUES (?,?)", ("1000000001", "12"))
            subprocess.run([
                sys.executable, str(SCRIPT), "--descriptions-db", str(descriptions),
                "--catalog-db", str(catalog), "--output", str(output),
                "--progress-source", "source", "--parser-delta-only",
            ], check=True, capture_output=True, text=True)
            packet = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(packet["candidate_labels"], ["12C"])

    def test_deduplicates_building_labels_and_builds_compound_source_url(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            descriptions = directory / "descriptions.db"
            catalog = directory / "catalog.db"
            output = directory / "packets.jsonl"
            with sqlite3.connect(descriptions) as connection:
                connection.executescript("""
                    CREATE TABLE progress (
                        source TEXT PRIMARY KEY, offset INTEGER, complete INTEGER, updated_at TEXT
                    );
                    INSERT INTO progress VALUES ('source', 2, 1, '2026-08-03');
                    CREATE TABLE descriptions (
                        job_filing_number TEXT PRIMARY KEY, bbl TEXT, address TEXT, zipcode TEXT,
                        description TEXT, filing_date TEXT, extracted_labels TEXT, status TEXT
                    );
                """)
                for ref in ("M1|I1|M1-I1-LA", "M2|I1|M2-I1-LA"):
                    connection.execute(
                        "INSERT INTO descriptions VALUES (?,?,?,?,?,?,?,?)",
                        (ref, "1000000001", "1 TEST STREET", "", "Apartment 4D",
                         "2026-08-03", json.dumps(["4D"]), "explicit_candidate"),
                    )
            with sqlite3.connect(catalog) as connection:
                connection.execute("CREATE TABLE units (bbl TEXT, normalized_unit TEXT)")
            subprocess.run([
                sys.executable, str(SCRIPT), "--descriptions-db", str(descriptions),
                "--catalog-db", str(catalog), "--output", str(output),
                "--progress-source", "source", "--dataset", "xxbr-ypig",
                "--id-field", "job_number,filing_number,permit_number",
                "--dedupe-building-labels",
            ], check=True, capture_output=True, text=True)
            packets = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertEqual(len(packets), 1)
            self.assertIn("job_number=M1", packets[0]["source_url"])
            self.assertIn("permit_number=M1-I1-LA", packets[0]["source_url"])


if __name__ == "__main__":
    unittest.main()
