"""Strict authority boundary tests for P10.2b browser input."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.capture_framing_profile import (  # noqa: E402
    INTENT,
    SUBMISSION_FORMAT,
)
from autospine_workbench.capture_framing_submission import (  # noqa: E402
    CaptureFramingSubmissionError,
    require_capture_framing_submission,
)


PACKAGE = "a" * 64
CANDIDATE = "b" * 64
P10_CANDIDATE = "c" * 64
P10_DECISION = "d" * 64


def submission(action="accept"):
    reasons = {
        "accept": "human-approved-automatic-capture-framing-v1",
        "adjust": "human-adjusted-capture-framing-v1",
        "reject": "human-rejected-capture-framing-v1",
        "unobservable": "human-marked-capture-framing-unobservable-v1",
    }
    return {
        "format": SUBMISSION_FORMAT,
        "format_version": 1,
        "intent": INTENT,
        "explicit_confirmation": True,
        "package_id": PACKAGE,
        "candidate_sha256": CANDIDATE,
        "p10_1_head": {
            "candidate_sha256": P10_CANDIDATE,
            "decision_sha256": P10_DECISION,
            "revision": 4,
        },
        "base_revision": 0,
        "previous_decision_sha256": None,
        "action": action,
        "reason_code": reasons[action],
        "world_viewport": (
            {"x": -2, "y": 3, "width": 1200, "height": 1200}
            if action == "adjust" else None
        ),
    }


class CaptureFramingSubmissionTests(unittest.TestCase):
    def test_accept_is_explicit_and_binds_package_candidate_and_p10_head(self):
        result = require_capture_framing_submission(submission())
        self.assertEqual(PACKAGE, result.package_id)
        self.assertEqual(CANDIDATE, result.candidate_sha256)
        self.assertEqual(P10_DECISION, result.p10_1_head["decision_sha256"])
        self.assertEqual("accept", result.action)
        self.assertIsNone(result.world_viewport)

    def test_adjust_normalizes_only_finite_positive_viewport(self):
        result = require_capture_framing_submission(submission("adjust"))
        self.assertEqual(
            {"x": -2.0, "y": 3.0, "width": 1200.0, "height": 1200.0},
            result.world_viewport,
        )
        for invalid in (0, -1, float("inf"), True):
            with self.subTest(invalid=invalid):
                value = submission("adjust")
                value["world_viewport"]["width"] = invalid
                with self.assertRaises(CaptureFramingSubmissionError):
                    require_capture_framing_submission(value)

    def test_confirmation_intent_head_and_predecessor_are_fail_closed(self):
        cases = []
        missing_confirmation = submission()
        missing_confirmation["explicit_confirmation"] = False
        cases.append(missing_confirmation)
        wrong_intent = submission()
        wrong_intent["intent"] = "capture-framing-preview-only"
        cases.append(wrong_intent)
        stale_head = submission()
        stale_head["p10_1_head"]["decision_sha256"] = "not-a-sha"
        cases.append(stale_head)
        wrong_predecessor = submission()
        wrong_predecessor["base_revision"] = 1
        cases.append(wrong_predecessor)
        extra = submission()
        extra["output_path"] = "E:/private/decision.json"
        cases.append(extra)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(
                CaptureFramingSubmissionError
            ):
                require_capture_framing_submission(value)

    def test_reject_and_unobservable_cannot_smuggle_a_viewport(self):
        for action in ("reject", "unobservable"):
            value = submission(action)
            value["world_viewport"] = {
                "x": 0, "y": 0, "width": 640, "height": 640,
            }
            with self.subTest(action=action), self.assertRaises(
                CaptureFramingSubmissionError
            ):
                require_capture_framing_submission(value)

    def test_reason_and_action_must_match_exactly(self):
        value = deepcopy(submission())
        value["reason_code"] = "human-adjusted-capture-framing-v1"
        with self.assertRaises(CaptureFramingSubmissionError):
            require_capture_framing_submission(value)


if __name__ == "__main__":
    unittest.main()
