"""Safe P10 failure classification without path or message disclosure."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.body_sway_headless_browser_inputs import (  # noqa: E402
    BodySwayHeadlessBrowserError,
)
from autospine_workbench.p10_capture_failure_codes import (  # noqa: E402
    classify_p10_capture_failure,
)
from autospine_workbench.p10_runtime_capture_v2_commands import (  # noqa: E402
    P10RuntimeCaptureV2CommandError,
)
from autospine_workbench.p10_runtime_capture_v2_runner import (  # noqa: E402
    P10RuntimeCaptureV2RunnerError,
)


class P10CaptureFailureCodeTests(unittest.TestCase):
    def test_nested_browser_exit_is_classified_without_exposing_message(self):
        leaf = BodySwayHeadlessBrowserError(
            "Headless browser exited without posting the exact capture"
        )
        runner = caused(P10RuntimeCaptureV2RunnerError("wrapped"), leaf)
        command = caused(P10RuntimeCaptureV2CommandError("private path"), runner)
        code = classify_p10_capture_failure(command)
        self.assertEqual("runtime_browser_exited_without_capture", code)
        self.assertNotIn("private", code)
        self.assertNotIn("path", code)

    def test_runtime_page_and_timeout_keep_distinct_safe_codes(self):
        values = {
            "Official runtime reported a terminal capture error":
                "runtime_page_reported_error",
            "Headless browser capture timed out": "runtime_browser_timeout",
        }
        for message, expected in values.items():
            with self.subTest(message=message):
                self.assertEqual(expected, classify_p10_capture_failure(
                    BodySwayHeadlessBrowserError(message)
                ))

    def test_unknown_failure_stays_bounded_and_generic(self):
        self.assertEqual(
            "runtime_capture_failed",
            classify_p10_capture_failure(RuntimeError(r"C:\\private\\error.log")),
        )


def caused(outer, inner):
    try:
        raise inner
    except BaseException as failure:
        try:
            raise outer from failure
        except BaseException as wrapped:
            return wrapped


if __name__ == "__main__":
    unittest.main()
