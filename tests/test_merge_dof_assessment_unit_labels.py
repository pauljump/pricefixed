import csv
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pricefixed.catalog import init_catalog_db


class DofAssessmentUnitMergeTest(unittest.TestCase):
    def test_merges_only_official_residential_unit_lot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "catalog.db"
            connection = init_catalog_db(database)
            connection.execute(
                "INSERT INTO sources VALUES (?,?,?,?,?)",
                ("nyc_dof_condo_units", "public_record", "test", "2026-08-03", "2026-08-03"),
            )
            connection.execute(
                "INSERT INTO official_unit_lots "
                "(unit_lot_bbl,condo_base_bbl,unit_designation,source,source_ref,document_id,record_status,first_seen,last_seen,raw_fields) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("1000411104", "1000410001", "", "nyc_dof_condo_units", "ref", "doc", "active", "2026-08-03", "2026-08-03", "{}"),
            )
            connection.commit()
            connection.close()
            source = root / "accepted.csv"
            fields = ("unit_lot_bbl", "unit_label", "normalized_unit", "address", "tax_class",
                      "building_class", "assessment_year", "assessment_period", "source_ref",
                      "source_url", "observed_at", "basis")
            with source.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerow({
                    "unit_lot_bbl": "1000411104", "unit_label": "4", "normalized_unit": "4",
                    "address": "54 PINE STREET", "tax_class": "2C", "building_class": "R1",
                    "assessment_year": "2027", "assessment_period": "3", "source_ref": "1000411104:2027:3",
                    "source_url": "https://example.test/assessment", "observed_at": "2026-08-03",
                    "basis": "fills_blank_condo_designation",
                })
            summary = root / "summary.json"
            subprocess.run(
                [sys.executable, "tools/merges/merge_dof_assessment_unit_labels.py",
                 "--csv", str(source), "--catalog-db", str(database), "--summary", str(summary), "--apply"],
                check=True, cwd=Path(__file__).resolve().parents[1],
            )
            self.assertEqual(json.loads(summary.read_text())["net_new_units"], 1)
            connection = sqlite3.connect(database)
            self.assertEqual(connection.execute("SELECT unit_label FROM units").fetchone()[0], "4")
            self.assertEqual(connection.execute("SELECT source FROM observations").fetchone()[0], SOURCE)
            connection.close()


SOURCE = "dof_property_assessment_unit_labels"
