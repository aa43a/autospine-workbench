from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.contracts import (  # noqa: E402
    ContractValidationError,
    ValidationIssue,
    normalize_override_request,
)
from autospine_workbench.split_decision_contracts import (  # noqa: E402
    normalize_split_decisions,
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
SHA_E = "e" * 64
SHA_F = "f" * 64
LAYERS = {"layer-footwear", "layer-legwear"}


def analysis() -> dict[str, str]:
    return {
        "layer_manifest_sha256": SHA_D,
        "resolved_snapshot_sha256": SHA_E,
        "split_spec_sha256": SHA_F,
        "algorithm_id": "nearest-limb-polyline",
        "algorithm_version": "1.1.0",
    }


def stored_decision(*, action: str = "accept") -> dict:
    item = {
        "action": action,
        "split_artifact_sha256": SHA_A,
        "operation_config_sha256": SHA_B,
        "review_target_sha256": SHA_C,
        "analysis": analysis(),
        "binding_status": "current",
    }
    if action == "reject":
        item["reason"] = "partition crosses the visible shoe opening"
    return item


def client_patch(decisions: dict | None = None) -> dict:
    return {
        "schema_version": "autospine-workbench.override/v3",
        "base_revision": 4,
        "joint_overrides": {},
        "joint_decisions": {},
        "split_decisions": decisions or {},
        "layer_overrides": {},
        "notes": "split review",
    }


def normalize(value: object, *, stored: bool = False):
    issues: list[ValidationIssue] = []
    result = normalize_split_decisions(
        value,
        layer_ids=LAYERS,
        issues=issues,
        stored=stored,
    )
    return result, issues


def normalize_patch(patch: dict, *, stored: bool = False) -> dict:
    _, normalized = normalize_override_request(
        patch,
        project_id="sample",
        current_revision=4,
        joint_ids=set(),
        layer_ids=LAYERS,
        canvas_width=100,
        canvas_height=200,
        stored=stored,
    )
    return normalized


class SplitDecisionNormalizationTests(unittest.TestCase):
    def test_client_actions_are_closed_deterministic_shapes(self) -> None:
        source = {
            "layer-legwear": {
                "reason": "reviewed silhouette",
                "split_artifact_sha256": SHA_A,
                "action": "accept",
            },
            "layer-footwear": {
                "reason": "incorrect left shoe partition",
                "action": "reject",
                "split_artifact_sha256": SHA_B,
            },
        }
        before = copy.deepcopy(source)

        result, issues = normalize(source)

        self.assertEqual([], issues)
        self.assertEqual(source, before)
        self.assertEqual(sorted(result), list(result))
        for item in result.values():
            self.assertEqual(sorted(item), list(item))
            self.assertNotIn("analysis", item)

    def test_persisted_shape_is_strict_and_roundtrip_safe(self) -> None:
        source = {
            "layer-legwear": stored_decision(),
            "layer-footwear": stored_decision(action="reject"),
        }

        first, first_issues = normalize(source, stored=True)
        second, second_issues = normalize(first, stored=True)

        self.assertEqual([], first_issues)
        self.assertEqual([], second_issues)
        self.assertEqual(first, second)
        self.assertEqual(
            sorted(first["layer-footwear"]["analysis"]),
            list(first["layer-footwear"]["analysis"]),
        )

        patch = client_patch(first)
        normalized = normalize_patch(patch, stored=True)
        replay = client_patch(normalized["split_decisions"])
        self.assertEqual(
            normalized["split_decisions"],
            normalize_patch(replay, stored=True)["split_decisions"],
        )

    def test_client_cannot_spoof_binder_derived_fields(self) -> None:
        for field, value in (
            ("operation_config_sha256", SHA_B),
            ("review_target_sha256", SHA_C),
            ("analysis", analysis()),
            ("binding_status", "current"),
        ):
            with self.subTest(field=field):
                raw = {
                    "layer-footwear": {
                        "action": "accept",
                        "split_artifact_sha256": SHA_A,
                        field: value,
                    }
                }
                result, issues = normalize(raw)
                self.assertEqual({}, result)
                self.assertEqual({"derived_field"}, {item.code for item in issues})

    def test_stored_shape_requires_every_revalidation_identity(self) -> None:
        required = (
            "operation_config_sha256",
            "review_target_sha256",
            "analysis",
            "binding_status",
        )
        for field in required:
            with self.subTest(field=field):
                item = stored_decision()
                del item[field]
                result, issues = normalize({"layer-footwear": item}, stored=True)
                self.assertEqual({}, result)
                self.assertIn("required", {issue.code for issue in issues})

        for field in analysis():
            with self.subTest(analysis_field=field):
                item = stored_decision()
                del item["analysis"][field]
                result, issues = normalize({"layer-footwear": item}, stored=True)
                self.assertEqual({}, result)
                self.assertTrue(issues)

    def test_hash_reason_action_layer_and_analysis_formats_fail_closed(self) -> None:
        raw = {
            "unknown-layer": stored_decision(),
            "layer-footwear": {
                **stored_decision(action="reject"),
                "action": "adjust",
                "split_artifact_sha256": "A" * 64,
                "operation_config_sha256": "0" * 63,
                "reason": " ",
                "surprise": True,
                "analysis": {
                    **analysis(),
                    "algorithm_id": "bad/provider",
                    "algorithm_version": "1 1",
                    "extra": "no",
                },
            },
        }

        result, issues = normalize(raw, stored=True)

        self.assertEqual({}, result)
        self.assertTrue(
            {"unknown_id", "unknown_field", "enum", "hash", "length", "id", "version"}
            .issubset({item.code for item in issues})
        )

    def test_legacy_versions_cannot_carry_split_decisions(self) -> None:
        for version in (
            "autospine-workbench.override/v1",
            "autospine-workbench.override/v2",
        ):
            with self.subTest(version=version):
                patch = client_patch()
                patch["schema_version"] = version
                with self.assertRaises(ContractValidationError) as caught:
                    normalize_patch(patch)
                self.assertIn("version", {item.code for item in caught.exception.issues})

                del patch["split_decisions"]
                normalized = normalize_patch(patch)
                self.assertEqual("autospine-workbench.override/v3", normalized["schema_version"])
                self.assertEqual({}, normalized["split_decisions"])

    def test_v3_canonical_output_always_contains_sorted_root(self) -> None:
        patch = client_patch(
            {
                "layer-legwear": {
                    "action": "accept",
                    "split_artifact_sha256": SHA_A,
                },
                "layer-footwear": {
                    "action": "reject",
                    "split_artifact_sha256": SHA_B,
                    "reason": "bad split",
                },
            }
        )
        normalized = normalize_patch(patch)
        self.assertEqual(sorted(normalized["split_decisions"]), list(normalized["split_decisions"]))


@unittest.skipIf(Draft202012Validator is None, "install the test extra for schema checks")
class SplitDecisionSchemaParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with (ROOT / "schemas" / "override-patch-v3.schema.json").open(
            "r", encoding="utf-8"
        ) as stream:
            cls.schema = json.load(stream)
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema)

    def test_client_schema_and_runtime_accept_the_same_action_shapes(self) -> None:
        for item in (
            {"action": "accept", "split_artifact_sha256": SHA_A},
            {
                "action": "reject",
                "split_artifact_sha256": SHA_A,
                "reason": "wrong silhouette",
            },
        ):
            with self.subTest(action=item["action"]):
                patch = client_patch({"layer-footwear": item})
                self.validator.validate(patch)
                self.assertEqual(item, normalize_patch(patch)["split_decisions"]["layer-footwear"])

    def test_schema_and_runtime_reject_missing_reason_and_spoofed_fields(self) -> None:
        invalid_items = (
            {"action": "reject", "split_artifact_sha256": SHA_A},
            {"action": "reject", "split_artifact_sha256": SHA_A, "reason": " "},
            {
                "action": "accept",
                "split_artifact_sha256": SHA_A,
                "operation_config_sha256": SHA_B,
            },
        )
        for item in invalid_items:
            with self.subTest(item=item):
                patch = client_patch({"layer-footwear": item})
                with self.assertRaises(ValidationError):
                    self.validator.validate(patch)
                with self.assertRaises(ContractValidationError):
                    normalize_patch(patch)

    def test_stored_definition_matches_runtime_shape(self) -> None:
        stored_schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$defs": self.schema["$defs"],
            "$ref": "#/$defs/splitDecisionStored",
        }
        validator = Draft202012Validator(stored_schema)
        item = stored_decision(action="reject")
        validator.validate(item)
        result, issues = normalize({"layer-footwear": item}, stored=True)
        self.assertEqual([], issues)
        self.assertEqual(item, result["layer-footwear"])


if __name__ == "__main__":
    unittest.main()
