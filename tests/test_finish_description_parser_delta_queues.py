import unittest
from unittest.mock import patch

from tools.local_model import finish_description_parser_delta_queues as module


class DescriptionParserDeltaQueueTest(unittest.TestCase):
    def test_queue_identities_and_sources_are_unique(self):
        self.assertEqual(len({row[0] for row in module.QUEUES}), len(module.QUEUES))
        self.assertEqual(len({row[1] for row in module.QUEUES}), len(module.QUEUES))
        self.assertTrue(all(row[6].endswith("_units") for row in module.QUEUES))

    def test_run_uses_checked_subprocess(self):
        with patch.object(module.subprocess, "run") as called:
            module.run("python", "script.py")
        called.assert_called_once_with(["python", "script.py"], check=True)


if __name__ == "__main__":
    unittest.main()
