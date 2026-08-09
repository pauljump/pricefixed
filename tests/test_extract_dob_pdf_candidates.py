import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.merges.extract_dob_pdf_candidates import load_text, parse_pdf_text, sidecar_path


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

    def test_ocr_sidecar_is_preferred_for_image_only_pdf(self):
        with TemporaryDirectory() as directory:
            pdf = Path(directory) / "M000034595.PDF"
            pdf.write_bytes(b"not a real PDF")
            text_dir = Path(directory) / "ocr"
            text_dir.mkdir()
            sidecar = text_dir / "M000034595.txt"
            sidecar.write_text("OCR CERTIFICATE", encoding="utf-8")

            self.assertEqual(sidecar_path(pdf, text_dir), sidecar)
            text, used = load_text(pdf, text_dir, pdftotext="missing-pdftotext")
            self.assertEqual(text, "OCR CERTIFICATE")
            self.assertEqual(used, sidecar)

    def test_c_of_o_capacity_row_code_is_not_an_apartment_label(self):
        row = {
            "property": "Peter Cooper Village",
            "target_address": "350 1 AVE",
            "target_bbl": "1009780001",
            "bis_premise": "350 1 AVENUE",
            "bis_bbl": "1009780001",
            "source_ref": "bis-co:1083679:co",
            "source_url": "index",
            "document_url": "doc",
            "identity_scope": "exact_premise",
        }
        text = (
            "CERTIFICATE OF OCCUPANCY\n350 1 AVENUE\n"
            "PERMISSIBLE USE AND OCCUPANCY\n"
            "APARTMENTS\n001\n74\nO.G.\n"
            "APARTMENTS PER FLOOR\nEIGHT (8) APARTMENTS PER FLOOR"
        )
        result = parse_pdf_text(row, text)
        self.assertEqual(result[0]["unit_label"], "")
        self.assertEqual(result[0]["status"], "no_explicit_unit_label")


if __name__ == "__main__":
    unittest.main()
