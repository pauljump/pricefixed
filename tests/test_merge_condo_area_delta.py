import csv
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pricefixed.catalog import init_catalog_db


class CondoAreaDeltaMergeTest(unittest.TestCase):
    def test_merges_cross_checked_unit_lot_with_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "catalog.db"
            init_catalog_db(database).close()
            source = root / "accepted.csv"
            row = {
                "unit_lot_bbl": "1001061207", "condo_base_bbl": "1001060004",
                "unit_label": "4F", "normalized_unit": "4F", "source_designation": "4F",
                "unit_lot": "1207", "condo_key": "102304", "bin": "1001359",
                "floor_text": "4TH FLOOR", "model": "D", "room_desc": "",
                "address": "272 WATER STREET", "object_id": "972", "observed_at": "2024-10-07",
                "basis": "matching_condo_area_and_acris_labels",
                "source_url": "https://data.cityofnewyork.us/resource/b5bf-t8kd.json?objectid=972",
                "acris_source_url": "https://data.cityofnewyork.us/resource/8h5j-fqxa.json?lot=1207",
            }
            with source.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=tuple(row))
                writer.writeheader()
                writer.writerow(row)
            summary = root / "summary.json"
            subprocess.run(
                [sys.executable, "tools/merges/merge_condo_area_delta.py", "--csv", str(source),
                 "--catalog-db", str(database), "--summary", str(summary), "--apply"],
                check=True, cwd=Path(__file__).resolve().parents[1],
            )
            self.assertEqual(json.loads(summary.read_text())["net_new_units"], 1)
            catalog = sqlite3.connect(database)
            self.assertEqual(catalog.execute("SELECT unit_label FROM units").fetchone()[0], "4F")
            self.assertEqual(
                catalog.execute("SELECT source FROM official_unit_lots").fetchone()[0],
                "nyc_dof_condo_area_units",
            )
            self.assertEqual(
                catalog.execute("SELECT evidence_grade FROM observations").fetchone()[0],
                "corroborated_public_records",
            )
            catalog.close()
