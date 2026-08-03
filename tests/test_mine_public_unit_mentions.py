import importlib.util
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "merges" / "mine_public_unit_mentions.py"
SPEC = importlib.util.spec_from_file_location("mine_public_unit_mentions", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return b"[]"


class PublicUnitMentionQueryTest(unittest.TestCase):
    def test_hpd_problems_only_queries_apartment_records(self):
        captured = {}

        def open_request(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            return _Response()

        with patch.object(MODULE, "urlopen", side_effect=open_request):
            MODULE.query_page(MODULE.SOURCES["hpd_problems"], 0, 100)

        query = parse_qs(urlparse(captured["url"]).query)
        self.assertIn("unit_type = 'APARTMENT'", query["$where"][0])
        self.assertEqual(captured["timeout"], 180)


if __name__ == "__main__":
    unittest.main()
