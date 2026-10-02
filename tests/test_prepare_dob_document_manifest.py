import unittest

from tools.merges.prepare_dob_document_manifest import build_manifest


INDEX_HTML = """
<html><body>
  <div>Premises: 342 1 AVENUE MANHATTAN BIN: 1082865 Block: 972 Lot: 1</div>
  <form action="CofoJobDocumentServlet" method="post">
    <input type="hidden" name="bin" value="1082865">
    <input type="hidden" name="passcofonumber" value="M000034595.PDF">
    <input type="hidden" name="requestid" value="2">
    <input type="hidden" name="cofomatadata1" value="COFO">
    <input type="hidden" name="cofomatadata2" value="M">
    <input type="hidden" name="cofomatadata3" value="000">
    <input type="hidden" name="cofomatadata4" value="034000">
    <input type="hidden" name="cofomatadata5" value="M000034595.PDF">
  </form>
</body></html>
"""


class PrepareDOBDocumentManifestTest(unittest.TestCase):
    def test_flags_shared_bbl_and_bbl_mismatch_without_importing_them(self):
        targets = [
            {"property": "Peter Cooper Village", "address": "342 1 AVENUE", "resolved_bbl": "1009780001"},
            {"property": "Stuyvesant Town", "address": "342 1 AVE", "resolved_bbl": "1009720001"},
            {"property": "Stuyvesant Town", "address": "340 1 AVE", "resolved_bbl": "1009720001"},
        ]
        rows = build_manifest(
            INDEX_HTML,
            "https://a810-bisweb.nyc.gov/bisweb/COsByLocationServlet?requestid=1&allbin=1082865",
            targets,
            "/tmp/dob-pdfs",
        )
        self.assertEqual(len(rows), 3)
        scopes = {(row["property"], row["target_address"]): row["identity_scope"] for row in rows}
        self.assertEqual(scopes[("Peter Cooper Village", "342 1 AVENUE")], "bbl_mismatch")
        self.assertEqual(scopes[("Stuyvesant Town", "342 1 AVE")], "exact_premise")
        self.assertEqual(scopes[("Stuyvesant Town", "340 1 AVE")], "shared_bbl")
        self.assertIn("CofoDocumentContentServlet", rows[0]["document_url"])
        self.assertEqual(rows[0]["source_ref"], "bis-co:1082865:M000034595.PDF")
