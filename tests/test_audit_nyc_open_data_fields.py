import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.merges.audit_nyc_open_data_fields import (
    TEXT_FIELD,
    UNIT_FIELD,
    candidate_rows,
    normalize_result,
    query_catalog,
    write_tsv,
)


class AuditNycOpenDataFieldsTest(unittest.TestCase):
    def test_normalizes_socrata_catalog_result(self):
        result = normalize_result({
            "resource": {
                "id": "abcd-1234", "name": "Homes", "description": "Test",
                "columns_name": ["BBL", "Apartment"],
                "columns_field_name": ["bbl", "apartment"],
                "updatedAt": "2026-08-03T00:00:00.000Z",
            },
            "classification": {"domain_category": "Housing"},
        })
        self.assertEqual(result["id"], "abcd-1234")
        self.assertEqual(result["fields"], ["bbl", "apartment"])
        self.assertEqual(result["category"], "Housing")

    def test_classifies_candidate_fields_and_building_identity(self):
        datasets = [{
            "id": "abcd-1234", "name": "Homes",
            "fields": ["bbl", "apartment", "job_description"],
        }]
        self.assertEqual(candidate_rows(datasets, UNIT_FIELD)[0][2:], ("bbl", "apartment"))
        self.assertEqual(
            candidate_rows(datasets, TEXT_FIELD)[0][2:], ("bbl", "job_description")
        )

    @patch("tools.merges.audit_nyc_open_data_fields.urlopen")
    def test_catalog_query_is_scoped_and_paged(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = b'{"results":[],"resultSetSize":0}'
        self.assertEqual(query_catalog(1000, 500)["results"], [])
        url = urlopen.call_args.args[0].full_url
        self.assertIn("search_context=data.cityofnewyork.us", url)
        self.assertIn("limit=500", url)
        self.assertIn("offset=1000", url)

    def test_writes_a_header_even_for_no_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.tsv"
            write_tsv(path, [])
            self.assertEqual(
                path.read_text(), "dataset\tname\tbuilding_fields\tcandidate_fields\n"
            )


if __name__ == "__main__":
    unittest.main()
