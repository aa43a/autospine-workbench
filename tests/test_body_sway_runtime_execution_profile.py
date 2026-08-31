"""Version and browser-lifetime tests for P10.3 v2 execution."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.body_sway_runtime_capture_profile import (  # noqa: E402
    BROWSER_FIXED_ARGUMENTS as FROZEN_V1_BROWSER_FIXED_ARGUMENTS,
)
from autospine_workbench.body_sway_runtime_execution_profile import (  # noqa: E402
    BROWSER_FIXED_ARGUMENTS,
    RUNNER_VERSION,
    body_sway_runtime_execution_runner_profile,
)


class BodySwayRuntimeExecutionProfileTests(unittest.TestCase):
    def test_v2_lifecycle_is_versioned_and_collector_terminal(self):
        profile = body_sway_runtime_execution_runner_profile()
        self.assertEqual("1.1.0", RUNNER_VERSION)
        self.assertEqual(RUNNER_VERSION, profile["version"])
        self.assertEqual("collector-terminal", profile["page_lifetime"])
        self.assertEqual(
            "collector-terminal-capture", profile["completion_signal"],
        )
        self.assertEqual(
            list(BROWSER_FIXED_ARGUMENTS), profile["fixed_browser_arguments"],
        )
        self.assertNotIn("--dump-dom", BROWSER_FIXED_ARGUMENTS)
        self.assertFalse(any(
            value.startswith("--virtual-time-budget=")
            for value in BROWSER_FIXED_ARGUMENTS
        ))

    def test_frozen_v1_arguments_are_not_rewritten(self):
        self.assertTrue(any(
            value.startswith("--virtual-time-budget=")
            for value in FROZEN_V1_BROWSER_FIXED_ARGUMENTS
        ))


if __name__ == "__main__":
    unittest.main()
