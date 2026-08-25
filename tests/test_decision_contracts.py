from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.contracts import ValidationIssue  # noqa: E402
from autospine_workbench.decision_contracts import (  # noqa: E402
    normalize_joint_decisions,
)

try:
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError
except ImportError:  # pragma: no cover - dependency-free runtime
    Draft202012Validator = None
    ValidationError = Exception


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64


def analysis() -> dict[str, str]:
    return {
        "provider": "pose-alpha-limb",
        "provider_version": "2",
        "input_sha256": SHA_B,
        "config_sha256": SHA_C,
        "run_sha256": SHA_D,
    }


def normalize(value: object, *, stored: bool = False):
    issues: list[ValidationIssue] = []
    result = normalize_joint_decisions(
        value,
        joint_ids={"elbow.left", "wrist.left", "knee.right", "ankle.right"},
        canvas_width=100,
        canvas_height=200,
        issues=issues,
        stored=stored,
    )
    return result, issues


def valid_patch() -> dict:
    return {
        "schema_version": "autospine-workbench.override/v2",
        "base_revision": 3,
        "joint_overrides": {},
        "joint_decisions": {
            "elbow.left": {
                "action": "accept",
                "candidate_artifact_sha256": SHA_A,
                "candidate_id": "elbow.left.pose.123abc",
            },
            "wrist.left": {
                "action": "adjust",
                "candidate_artifact_sha256": SHA_A,
                "candidate_id": "wrist.left.contact.123abc",
                "final_xy": [20.5, 70.25],
                "reason": "move to the visible wrist seam",
            },
            "knee.right": {
                "action": "reject",
                "candidate_artifact_sha256": SHA_A,
                "candidate_id": "knee.right.pose.123abc",
                "reason": "candidate follows the skirt edge",
            },
            "ankle.right": {
                "action": "unobservable",
                "candidate_artifact_sha256": SHA_A,
                "reason": "foot is hidden by the dress",
            },
        },
        "layer_overrides": {},
        "notes": "reviewed",
    }


class JointDecisionNormalizationTests(unittest.TestCase):
    def test_client_actions_normalize_deterministically(self) -> None:
        decisions = valid_patch()["joint_decisions"]
        result, issues = normalize(decisions)

        self.assertEqual([], issues)
        self.assertEqual(sorted(result), list(result))
        self.assertEqual([20.5, 70.25], result["wrist.left"]["final_xy"])
        self.assertNotIn("final_xy", result["elbow.left"])
        self.assertNotIn("candidate_id", result["ankle.right"])
        for item in result.values():
            self.assertEqual(sorted(item), list(item))

    def test_stored_accept_requires_derived_point_and_analysis(self) -> None:
        raw = {
            "elbow.left": {
                "action": "accept",
                "candidate_artifact_sha256": SHA_A,
                "candidate_id": "elbow.left.pose.123abc",
                "final_xy": [10, 20],
                "analysis": analysis(),
            }
        }
        result, issues = normalize(raw, stored=True)

        self.assertEqual([], issues)
        self.assertEqual([10.0, 20.0], result["elbow.left"]["final_xy"])
        self.assertEqual(sorted(analysis()), list(result["elbow.left"]["analysis"]))

        raw["elbow.left"].pop("final_xy")
        raw["elbow.left"].pop("analysis")
        result, issues = normalize(raw, stored=True)
        self.assertEqual({}, result)
        self.assertEqual({"required"}, {issue.code for issue in issues})

    def test_client_cannot_spoof_binder_derived_fields(self) -> None:
        raw = {
            "elbow.left": {
                "action": "accept",
                "candidate_artifact_sha256": SHA_A,
                "candidate_id": "elbow.left.pose.123abc",
                "final_xy": [10, 20],
                "analysis": analysis(),
            }
        }
        result, issues = normalize(raw)

        self.assertEqual({}, result)
        self.assertTrue(issues)
        self.assertEqual({"derived_field"}, {issue.code for issue in issues})

    def test_action_specific_candidate_point_and_reason_rules(self) -> None:
        invalid = {
            "elbow.left": {
                "action": "accept",
                "candidate_artifact_sha256": SHA_A,
            },
            "wrist.left": {
                "action": "adjust",
                "candidate_artifact_sha256": SHA_A,
                "candidate_id": "wrist.left.pose.x",
                "reason": "needed but point is absent",
            },
            "knee.right": {
                "action": "reject",
                "candidate_artifact_sha256": SHA_A,
                "candidate_id": "knee.right.pose.x",
                "final_xy": [1, 2],
            },
            "ankle.right": {
                "action": "unobservable",
                "candidate_artifact_sha256": SHA_A,
                "candidate_id": "ankle.right.pose.x",
                "reason": "   ",
            },
        }
        result, issues = normalize(invalid)

        self.assertEqual({}, result)
        codes = {issue.code for issue in issues}
        self.assertTrue({"required", "forbidden", "length"}.issubset(codes))

    def test_strict_hash_id_coordinate_analysis_and_unknown_validation(self) -> None:
        raw = {
            "elbow.left": {
                "action": "adjust",
                "candidate_artifact_sha256": "A" * 64,
                "candidate_id": "../escape",
                "final_xy": [float("nan"), 201],
                "reason": "x" * 1001,
                "surprise": True,
                "analysis": {
                    **analysis(),
                    "provider": "bad/provider",
                    "run_sha256": "0" * 63,
                    "extra": "no",
                },
            }
        }
        result, issues = normalize(raw, stored=True)

        self.assertEqual({}, result)
        codes = {issue.code for issue in issues}
        self.assertTrue({"unknown_field", "hash", "id", "shape", "length"}.issubset(codes))

    def test_unknown_or_non_string_joint_keys_are_rejected(self) -> None:
        result, issues = normalize(
            {
                "hip.left": {
                    "action": "unobservable",
                    "candidate_artifact_sha256": SHA_A,
                    "reason": "not in contract fixture",
                },
                3: {},
            }
        )
        self.assertEqual({}, result)
        self.assertEqual({"type", "unknown_id"}, {issue.code for issue in issues})


@unittest.skipIf(Draft202012Validator is None, "install the test extra for schema checks")
class JointDecisionSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with (ROOT / "schemas" / "override-patch-v2.schema.json").open(
            "r", encoding="utf-8"
        ) as stream:
            cls.schema = json.load(stream)
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema)

    def test_v2_client_patch_validates(self) -> None:
        self.validator.validate(valid_patch())

    def test_if_then_rules_reject_derived_or_missing_fields(self) -> None:
        cases = []
        accepted = valid_patch()
        accepted["joint_decisions"]["elbow.left"]["final_xy"] = [1, 2]
        cases.append(accepted)

        adjusted = valid_patch()
        adjusted["joint_decisions"]["wrist.left"].pop("reason")
        cases.append(adjusted)

        unobservable = valid_patch()
        unobservable["joint_decisions"]["ankle.right"]["candidate_id"] = "ankle.right.x"
        cases.append(unobservable)

        spoofed = valid_patch()
        spoofed["joint_decisions"]["elbow.left"]["analysis"] = analysis()
        cases.append(spoofed)

        for document in cases:
            with self.subTest(document=document):
                with self.assertRaises(ValidationError):
                    self.validator.validate(document)


if __name__ == "__main__":
    unittest.main()
