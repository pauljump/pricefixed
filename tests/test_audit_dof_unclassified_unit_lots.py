import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from tools.merges.audit_dof_unclassified_unit_lots import audit, query


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class AuditDofUnclassifiedUnitLotsTest(unittest.TestCase):
    @patch("tools.merges.audit_dof_unclassified_unit_lots.urlopen")
    def test_query_preserves_bounded_historical_source_url(self, urlopen):
        urlopen.return_value = _Response([])
        rows, source_url = query(["1000000001"], "2017")
        self.assertEqual(rows, [])
        parsed = parse_qs(urlparse(source_url).query)
        self.assertEqual(parsed["$select"][0], "bble,txcl,bldgcl,year4,hnum_lo,str_name,zip")
        self.assertIn("year4='2017'", parsed["$where"][0])
        self.assertIn("1000000001", parsed["$where"][0])

    @patch("tools.merges.audit_dof_unclassified_unit_lots.query")
    def test_keeps_no_match_visible_and_classifies_only_review_evidence(self, query_mock):
        query_mock.side_effect = [
            ([{"bble": "1000000001", "txcl": "2", "bldgcl": "R4",
               "year4": "2017", "hnum_lo": "10", "str_name": "MAIN ST", "zip": "10001"}],
             "https://data.example/2017"),
            ([], "https://data.example/2016"),
        ]
        targets = {
            "1000000001": {"unit_lot_bbl": "1000000001", "official_unit_designation": "5A"},
            "1000000002": {"unit_lot_bbl": "1000000002", "official_unit_designation": "5B"},
        }
        rows = audit(targets, ["2017", "2016"], chunk_size=10, pause=0)
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["status"], "historical_residential_tax_class")
        self.assertEqual(rows[1]["status"], "no_historical_match")
        self.assertEqual(rows[0]["source_url"], "https://data.example/2017")
        self.assertEqual(rows[2]["status"], "no_historical_match")
        self.assertEqual(rows[3]["status"], "no_historical_match")


if __name__ == "__main__":
    unittest.main()
