import unittest
import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

from pricefixed.catalog import init_catalog_db
from tools.merges.mine_dof_historical_assessment_unit_labels import (
    classify, house_number, progress_source, query,
)


class HistoricalDofAssessmentUnitLabelTest(unittest.TestCase):
    def test_strips_dof_house_number_padding(self):
        self.assertEqual(house_number("000000000038"), "38")
        self.assertEqual(house_number("000000030-44"), "30-44")

    @patch("tools.merges.mine_dof_historical_assessment_unit_labels.urlopen")
    def test_query_is_limited_to_residential_single_unit_lots(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = b"[]"

        self.assertEqual(query("2017", 0, 100), [])
        url = urlopen.call_args.args[0].full_url
        self.assertIn("year4%3D%272017%27", url)
        self.assertIn("res_unit%3D1", url)
        self.assertIn("txcl+in", url)

    @patch("tools.merges.mine_dof_historical_assessment_unit_labels.urlopen")
    def test_query_can_audit_a_separate_historical_tax_class_table(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = b"[]"
        self.assertEqual(query("2017", 0, 100, "m8p6-tp4b"), [])
        self.assertIn("/m8p6-tp4b.json", urlopen.call_args.args[0].full_url)
        self.assertEqual(
            progress_source("m8p6-tp4b", "2017"),
            "dof_historical_assessment_units_m8p6-tp4b_2017",
        )

    def test_rejects_a_historical_alias_on_an_identified_unit_lot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_path = root / "catalog.db"
            catalog = init_catalog_db(catalog_path)
            catalog.execute(
                "INSERT INTO official_unit_lots "
                "(unit_lot_bbl,unit_designation,source,source_ref,document_id,record_status,first_seen,last_seen,raw_fields) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                ("4005771071", None, "test", "lot", "doc", "reported", "2026-08-03", "2026-08-03", "{}"),
            )
            catalog.execute(
                "INSERT INTO units VALUES (?,?,?,?,?,?)",
                ("unit-existing", "4005771071", "5L", "5L", "2026-08-03", "2026-08-03"),
            )
            catalog.commit()
            catalog.close()

            stage_path = root / "stage.db"
            stage = sqlite3.connect(stage_path)
            stage.executescript("""
                CREATE TABLE assessment_units (
                    parid TEXT PRIMARY KEY, aptno TEXT, tax_class TEXT, building_class TEXT,
                    assessment_year TEXT, address TEXT, zipcode TEXT
                );
                CREATE TABLE progress (source TEXT PRIMARY KEY, offset INTEGER, complete INTEGER, updated_at TEXT);
            """)
            stage.execute(
                "INSERT INTO assessment_units VALUES (?,?,?,?,?,?,?)",
                ("4005771071", "730", "2", "R4", "2017", "30-44 29 STREET", "11102"),
            )
            stage.execute(
                "INSERT INTO progress VALUES (?,?,?,?)",
                ("dof_historical_assessment_units_2017", 1, 1, "2026-08-03"),
            )
            stage.commit()
            stage.close()

            summary = root / "summary.json"
            classify(
                stage_path, catalog_path, root / "accepted.csv", root / "rejected.csv",
                summary, "2017",
            )
            report = json.loads(summary.read_text())
            self.assertEqual(report["net_new_candidates"], 0)
            self.assertEqual(
                report["rejection_reasons"]["official_unit_lot_already_has_unit"], 1
            )
