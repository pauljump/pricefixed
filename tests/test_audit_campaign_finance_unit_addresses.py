import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from tools.merges.audit_campaign_finance_unit_addresses import (
    init_db,
    query_page,
    resolve_residential_pad_bbl,
    summary,
)


class AuditCampaignFinanceUnitAddressesTest(unittest.TestCase):
    def test_requires_unique_pad_zip_match_and_residential_capacity(self):
        connection = sqlite3.connect(":memory:")
        connection.executescript("""
            CREATE TABLE addresses (bbl TEXT, normalized TEXT, zipcode TEXT, source TEXT);
            CREATE TABLE buildings (bbl TEXT, units_res INTEGER);
            INSERT INTO addresses VALUES ('1000000001','1 ASTOR PL','10003','nyc_pad');
            INSERT INTO buildings VALUES ('1000000001',12);
        """)
        self.assertEqual(
            resolve_residential_pad_bbl(connection, "1 Astor Place", "10003-0001"),
            "1000000001",
        )
        connection.execute(
            "INSERT INTO addresses VALUES ('1000000002','1 ASTOR PL','10003','nyc_pad')"
        )
        connection.execute("INSERT INTO buildings VALUES ('1000000002',8)")
        self.assertEqual(resolve_residential_pad_bbl(connection, "1 Astor Pl", "10003"), "")

    @patch("tools.merges.audit_campaign_finance_unit_addresses.urlopen")
    def test_query_does_not_request_person_or_payment_fields(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = b"[]"
        rows, url = query_page(0, 100)
        self.assertEqual(rows, [])
        self.assertIn("c_code%3D%27IND%27", url)
        selected = parse_qs(urlparse(url).query)["$select"][0].split(",")
        for field in ("name", "amnt", "occupation", "empname"):
            self.assertNotIn(field, selected)

    def test_summary_never_claims_a_catalog_write(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = sqlite3.connect(Path(directory) / "audit.db")
            init_db(connection)
            result = summary(connection)
            self.assertEqual(result["catalog_writes"], 0)
            self.assertEqual(result["net_new_policy_review"], 0)
            connection.close()


if __name__ == "__main__":
    unittest.main()
