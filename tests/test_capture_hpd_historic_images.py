import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.merges.capture_hpd_historic_images import capture


class _Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


class CaptureHPDHistoricImagesTest(unittest.TestCase):
    def test_captures_pdf_and_preserves_source_identifiers(self):
        pdf = b"%PDF-1.4\nunit labels require human review\n"
        calls = []
        responses = [
            {"token": "test-token"},
            {"responseData": [{
                "buildingId": 576, "imageSeqNo": 606251, "docName": "3594781",
                "docDescription": "I-CARD IMAGE(S)", "dateTaken": "02/15/2008 00:00:00",
                "docTypeId": 53, "subDocTypeId": 73, "docId": 3594781, "fileType": "pdf",
            }]},
            {"responseData": {"documentBytes": base64.b64encode(pdf).decode()}},
        ]

        def fake_urlopen(request, timeout):
            calls.append((request.full_url, request.get_method(), request.headers))
            return _Response(responses.pop(0))

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "tools.merges.capture_hpd_historic_images.urlopen", fake_urlopen
        ):
            manifest = capture(576, temp_dir)
            output = Path(temp_dir)
            self.assertEqual(len(manifest["cards"]), 1)
            card = manifest["cards"][0]
            self.assertEqual(card["source_ref"], "hpd-icard:576:606251")
            self.assertEqual((output / "Icard_606251.pdf").read_bytes(), pdf)
            self.assertTrue((output / "historic-image-list-576.json").exists())
            self.assertTrue((output / "historic-image-manifest-576.json").exists())
            self.assertIn("historicimage/list/576", calls[1][0])
            self.assertIn("documents/content/606251/3594781/53/73", calls[2][0])
            self.assertEqual(calls[1][2]["Apikey"], "Bearer test-token")


if __name__ == "__main__":
    unittest.main()
