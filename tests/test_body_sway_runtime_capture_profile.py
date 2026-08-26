"""Contract tests for the Windows-only official-runtime capture runner."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.body_sway_runtime_capture_profile import (  # noqa: E402
    BROWSER_FIXED_ARGUMENTS,
    body_sway_runtime_capture_runner_profile,
)


class BodySwayRuntimeCaptureProfileTests(unittest.TestCase):
    def test_schema_and_profile_pin_the_same_windows_only_runner(self):
        profile = body_sway_runtime_capture_runner_profile()
        schema = json.loads(
            (ROOT / "schemas" / "body-sway-runtime-capture-v1.schema.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(profile, schema["properties"]["runner"]["const"])
        self.assertEqual("windows", profile["supported_host_os"])
        self.assertEqual(
            {"windows"}, set(profile["process_tree_control"])
        )

    def test_no_sandbox_is_fixed_and_its_owned_job_reason_is_explicit(self):
        profile = body_sway_runtime_capture_runner_profile()
        self.assertEqual(
            "disabled-for-owned-job", profile["chromium_sandbox"]
        )
        self.assertEqual(
            "required-for-owned-inner-job-chromium-compatibility",
            profile["chromium_sandbox_reason"],
        )
        self.assertEqual(1, BROWSER_FIXED_ARGUMENTS.count("--no-sandbox"))
        self.assertIn("--no-sandbox", profile["fixed_browser_arguments"])

    def test_file_lease_claim_is_limited_to_transaction_stability(self):
        stability = body_sway_runtime_capture_runner_profile()[
            "browser_executable_stability"
        ]
        self.assertEqual(
            "before-snapshot-through-final-exact-replay", stability["scope"]
        )
        self.assertFalse(stability["mapped_page_identity_claimed"])


if __name__ == "__main__":
    unittest.main()
