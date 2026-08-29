"""Strict P10.1 browser-submission boundary tests."""

from __future__ import annotations

from copy import deepcopy
import unittest

from autospine_workbench.idle_behavior_review_submission import (
    IdleBehaviorReviewSubmissionError,
    require_idle_behavior_review_submission,
)


def valid_submission(**changes):
    value = {
        "format": "autospine-idle-behavior-review-submission",
        "format_version": 1,
        "intent": "body-sway-human-review-v1",
        "explicit_confirmation": True,
        "package_id": "a" * 64,
        "candidate_sha256": "b" * 64,
        "base_revision": 0,
        "previous_decision_sha256": None,
        "action": "adjust",
        "reason_code": "human-approved-assisted-draft-v1",
        "parameters": {
            "cycles": 2,
            "per_bone_amplitude_deg": _rows((0.8, 0.7, 0.4, 0.2)),
            "per_bone_phase_fraction": _rows((0.0, 0.04, 0.08, 0.12)),
        },
    }
    value.update(changes)
    return value


def _rows(values):
    bones = ("pelvis-spine", "spine-chest", "chest-neck", "neck-head")
    return [
        {"bone_id": bone, "value": value}
        for bone, value in zip(bones, values, strict=True)
    ]


class IdleBehaviorReviewSubmissionTests(unittest.TestCase):
    def test_confirmed_adjustment_is_copied_and_normalized(self):
        source = valid_submission()
        result = require_idle_behavior_review_submission(source)
        source["parameters"]["cycles"] = 7
        self.assertEqual(2, result.parameters["cycles"])
        self.assertEqual("adjust", result.action)

    def test_explicit_confirmation_and_exact_fields_are_required(self):
        for change in (
            {"explicit_confirmation": False},
            {"explicit_confirmation": 1},
            {"intent": "wrong"},
            {"format_version": True},
        ):
            with self.subTest(change=change), self.assertRaises(
                IdleBehaviorReviewSubmissionError
            ):
                require_idle_behavior_review_submission(
                    valid_submission(**change)
                )
        extra = valid_submission()
        extra["reviewer"] = "browser"
        with self.assertRaises(IdleBehaviorReviewSubmissionError):
            require_idle_behavior_review_submission(extra)

    def test_predecessor_action_and_parameters_are_cross_checked(self):
        stale = valid_submission(base_revision=1)
        with self.assertRaises(IdleBehaviorReviewSubmissionError):
            require_idle_behavior_review_submission(stale)
        valid_reject = valid_submission(
            action="reject",
            reason_code="human-declined-body-sway-v1",
            parameters=None,
        )
        self.assertEqual(
            "reject",
            require_idle_behavior_review_submission(valid_reject).action,
        )
        invalid = deepcopy(valid_reject)
        invalid["parameters"] = valid_submission()["parameters"]
        with self.assertRaises(IdleBehaviorReviewSubmissionError):
            require_idle_behavior_review_submission(invalid)

    def test_per_bone_order_finiteness_and_nonzero_amplitude_fail_closed(self):
        cases = []
        swapped = valid_submission()
        swapped["parameters"]["per_bone_amplitude_deg"].reverse()
        cases.append(swapped)
        nonfinite = valid_submission()
        nonfinite["parameters"]["per_bone_phase_fraction"][0]["value"] = float("nan")
        cases.append(nonfinite)
        zero = valid_submission()
        for row in zero["parameters"]["per_bone_amplitude_deg"]:
            row["value"] = 0
        cases.append(zero)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(
                IdleBehaviorReviewSubmissionError
            ):
                require_idle_behavior_review_submission(value)


if __name__ == "__main__":
    unittest.main()
