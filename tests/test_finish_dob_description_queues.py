import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "local_model" / "finish_dob_description_queues.py"
SPEC = importlib.util.spec_from_file_location("finish_dob_description_queues", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DobQueueOrchestratorTest(unittest.TestCase):
    def test_run_uses_checked_subprocess(self):
        with patch.object(MODULE.subprocess, "run") as called:
            MODULE.run("python", "script.py")
        called.assert_called_once_with(["python", "script.py"], check=True)


if __name__ == "__main__":
    unittest.main()
