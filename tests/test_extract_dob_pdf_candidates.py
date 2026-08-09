import unittest

from tools.merges.extract_dob_pdf_candidates import parse_pdf_text


class ExtractDOBPdfCandidatesTest(unittest.TestCase):
    def test_exact_address_label_is_review_candidate(self):
        row = {
            "property": "Stuyvesant Town",
            "target_address": "342 1 AVE",
            "target_bbl": "1009720001",
            "bis_premise": "342 1 AVENUE",
            "bis_bbl": "1009720001",
            "source_ref": "bis-co:1082865:M000034595.PDF",
            "source_url": "https://example.test/index",
            "document_url": "https://example.test/document.pdf",
            "local_pdf": "/tmp/document.pdf",
            "identity_scope": "exact_premise",
        }
        result = parse_pdf_text(row, "CERTIFICATE OF OCCUPANCY\n342 1 AVENUE\nAPARTMENTS 5D AND 6D")
        self.assertEqual([r["unit_label"] for r in result], ["5D", "6D"])
        self.assertTrue(all(r["status"] == "review_candidate" for r in result))
        self.assertTrue(all(r["text_address_match"] == "yes" for r in result))
        self.assertTrue(all(r["source_url"] == row["document_url"] for r in result))

    def test_shared_bbl_never_becomes_exact_candidate(self):
        row = {
            "property": "Stuyvesant Town", "target_address": "340 1 AVE", "target_bbl": "1009720001",
            "bis_premise": "342 1 AVENUE", "bis_bbl": "1009720001",
            "source_ref": "co", "source_url": "index", "document_url": "doc",
            "identity_scope": "shared_bbl",
        }
        result = parse_pdf_text(row, "APARTMENT 5D")
        self.assertEqual(result[0]["status"], "shared_bbl_candidate")
        self.assertEqual(result[0]["identity_scope"], "shared_bbl")


if __name__ == "__main__":
    unittest.main()
