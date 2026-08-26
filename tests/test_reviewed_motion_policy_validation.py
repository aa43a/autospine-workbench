"""Standalone ReviewedMotionPolicy v1 validator and schema tests."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from autospine_workbench.reviewed_motion_policy_validation import (
    ReviewedMotionPolicyValidationError,
    require_reviewed_motion_policy,
    reviewed_motion_policy_sha256,
)

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test dependency
    Draft202012Validator = None


ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 64


def _source():
    return {
        "motion_policy_decision_sha256": SHA,
        "foot_lock_candidates_sha256": SHA,
        "depth_order_candidates_sha256": SHA,
        "depth_pair_policy_sha256": SHA,
        "p8": {
            field: SHA for field in (
                "projected_motion_sha256", "bundle_sha256", "camera_sha256",
                "run_sha256", "legacy_motion_sha256", "p7_motion_sha256",
                "p7_bundle_sha256", "p7_run_sha256",
            )
        },
        "p5": {
            field: SHA for field in (
                "target_profile_sha256", "instance_sha256", "run_sha256",
                "retarget_report_sha256", "mesh_regression_sha256",
                "bundle_sha256",
            )
        },
        "p3": {
            field: SHA for field in (
                "base_rig_sha256", "base_bundle_sha256",
                "layer_manifest_sha256", "resolved_project_sha256",
                "rig_sha256", "run_sha256", "probes_sha256",
                "visuals_sha256", "bundle_sha256",
            )
        },
    }


def valid_policy(*, loop=False):
    slot_keys = [{"tick": 0, "slot_ids": ["body", "arm", "face"]}]
    if loop:
        slot_keys.extend([
            {"tick": 50, "slot_ids": ["body", "face", "arm"]},
            {"tick": 100, "slot_ids": ["body", "arm", "face"]},
        ])
    return {
        "format": "autospine-reviewed-motion-policy",
        "format_version": 1,
        "project_id": "sample.project",
        "clip_id": "wave-01",
        "source": _source(),
        "timing": {
            "ticks_per_second": 1_000_000,
            "duration_ticks": 100,
            "loop": loop,
            "frame_count": 3,
        },
        "semantics": {
            "root_correction": "additive-target-root-translation",
            "root_unit": "pixel",
            "root_interpolation": "linear",
            "slot_order": "full-back-to-front-permutation",
            "slot_interpolation": "stepped",
            "attachment_switching": False,
            "raster_truth_claimed": False,
        },
        "root_correction_keys": [
            {
                "tick": 0,
                "correction_xy_px": [0.0, 0.0],
                "incoming_interpolation": "linear",
            },
            {
                "tick": 100,
                "correction_xy_px": [0.0, 0.0] if loop else [2.5, -1.0],
                "incoming_interpolation": "linear",
            },
        ],
        "slot_order": {
            "setup_slot_ids": ["body", "arm", "face"],
            "keys": slot_keys,
        },
    }


class ReviewedMotionPolicyValidationTests(unittest.TestCase):
    def assert_invalid(self, mutate, *, loop=False):
        document = valid_policy(loop=loop)
        mutate(document)
        with self.assertRaises(ReviewedMotionPolicyValidationError):
            require_reviewed_motion_policy(document)

    def test_valid_nonloop_and_loop_documents(self):
        require_reviewed_motion_policy(valid_policy())
        require_reviewed_motion_policy(valid_policy(loop=True))
        static_loop = valid_policy(loop=True)
        static_loop["slot_order"]["keys"] = static_loop["slot_order"]["keys"][:1]
        require_reviewed_motion_policy(static_loop)

    def test_hash_is_canonical_and_validation_gated(self):
        document = valid_policy()
        reordered = json.loads(json.dumps(document, sort_keys=True))
        self.assertEqual(
            reviewed_motion_policy_sha256(document),
            reviewed_motion_policy_sha256(reordered),
        )
        reordered["format_version"] = 2
        with self.assertRaises(ReviewedMotionPolicyValidationError):
            reviewed_motion_policy_sha256(reordered)

    def test_top_source_and_nested_source_are_exact(self):
        cases = [
            lambda row: row.__setitem__("extra", True),
            lambda row: row["source"].pop("motion_policy_decision_sha256"),
            lambda row: row["source"].__setitem__("extra", SHA),
            lambda row: row["source"]["p8"].pop("camera_sha256"),
            lambda row: row["source"]["p5"].__setitem__("extra", SHA),
            lambda row: row["source"]["p3"].__setitem__("rig_sha256", SHA.upper()),
        ]
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)

    def test_identity_timing_and_semantics_fail_closed(self):
        cases = [
            lambda row: row.__setitem__("project_id", "unsafe id"),
            lambda row: row["timing"].__setitem__("ticks_per_second", 1000),
            lambda row: row["timing"].__setitem__("duration_ticks", True),
            lambda row: row["timing"].__setitem__("duration_ticks", 600_000_001),
            lambda row: row["timing"].__setitem__("frame_count", 1),
            lambda row: row["timing"].__setitem__("loop", 0),
            lambda row: row["timing"].__setitem__("extra", 1),
            lambda row: row["semantics"].__setitem__("root_unit", "meter"),
            lambda row: row["semantics"].__setitem__("raster_truth_claimed", True),
            lambda row: row["semantics"].pop("attachment_switching"),
        ]
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)

    def test_root_keys_require_bounded_linear_clip_endpoints(self):
        cases = [
            lambda row: row.__setitem__("root_correction_keys", []),
            lambda row: row["root_correction_keys"][0].__setitem__("tick", 1),
            lambda row: row["root_correction_keys"][-1].__setitem__("tick", 99),
            lambda row: row["root_correction_keys"][-1].__setitem__("tick", 0),
            lambda row: row["root_correction_keys"][-1].__setitem__("tick", True),
            lambda row: row["root_correction_keys"][0].__setitem__(
                "incoming_interpolation", "stepped"
            ),
            lambda row: row["root_correction_keys"][0].__setitem__(
                "correction_xy_px", [0.0]
            ),
            lambda row: row["root_correction_keys"][0].__setitem__(
                "correction_xy_px", [float("nan"), 0.0]
            ),
            lambda row: row["root_correction_keys"][0].__setitem__(
                "correction_xy_px", [1_000_000_000_001, 0.0]
            ),
            lambda row: row["root_correction_keys"][0].__setitem__("extra", 0),
        ]
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)

    def test_loop_root_endpoints_must_be_zero(self):
        self.assert_invalid(
            lambda row: row["root_correction_keys"][0].__setitem__(
                "correction_xy_px", [1.0, 0.0]
            ),
            loop=True,
        )
        self.assert_invalid(
            lambda row: row["root_correction_keys"][-1].__setitem__(
                "correction_xy_px", [0.0, -1.0]
            ),
            loop=True,
        )

    def test_slot_order_requires_exact_full_permutations(self):
        cases = [
            lambda row: row["slot_order"].__setitem__("setup_slot_ids", []),
            lambda row: row["slot_order"].__setitem__(
                "setup_slot_ids", ["body", "body"]
            ),
            lambda row: row["slot_order"]["setup_slot_ids"].__setitem__(0, "bad id"),
            lambda row: row["slot_order"].__setitem__("keys", []),
            lambda row: row["slot_order"]["keys"][0].__setitem__("tick", 1),
            lambda row: row["slot_order"]["keys"][0].__setitem__(
                "slot_ids", ["body", "face", "arm"]
            ),
            lambda row: row["slot_order"]["keys"][0].__setitem__(
                "slot_ids", ["body", "arm", "other"]
            ),
            lambda row: row["slot_order"]["keys"][0].__setitem__("extra", 1),
            lambda row: row["slot_order"].__setitem__("extra", 1),
        ]
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)

    def test_slot_ticks_are_sorted_and_adjacent_orders_differ(self):
        self.assert_invalid(
            lambda row: row["slot_order"]["keys"].extend([
                {"tick": 40, "slot_ids": ["body", "face", "arm"]},
                {"tick": 40, "slot_ids": ["body", "arm", "face"]},
            ])
        )
        self.assert_invalid(
            lambda row: row["slot_order"]["keys"].append(
                {"tick": 50, "slot_ids": ["body", "arm", "face"]}
            )
        )
        self.assert_invalid(
            lambda row: row["slot_order"]["keys"].append(
                {"tick": 101, "slot_ids": ["body", "face", "arm"]}
            )
        )

    def test_loop_slot_order_requires_duration_setup_reset(self):
        self.assert_invalid(
            lambda row: row["slot_order"]["keys"].pop(), loop=True
        )
        self.assert_invalid(
            lambda row: row["slot_order"]["keys"][-1].__setitem__(
                "slot_ids", ["body", "face", "arm"]
            ),
            loop=True,
        )
        self.assert_invalid(
            lambda row: row["slot_order"].__setitem__("keys", [
                {"tick": 0, "slot_ids": ["body", "arm", "face"]},
                {"tick": 100, "slot_ids": ["body", "arm", "face"]},
            ]),
            loop=True,
        )

    def test_document_byte_cap_is_enforced(self):
        with patch(
            "autospine_workbench.reviewed_motion_policy_validation.MAX_DOCUMENT_BYTES",
            1,
        ):
            with self.assertRaises(ReviewedMotionPolicyValidationError):
                require_reviewed_motion_policy(valid_policy())

    def test_non_mapping_and_non_json_values_fail_closed(self):
        with self.assertRaises(ReviewedMotionPolicyValidationError):
            require_reviewed_motion_policy(None)
        document = valid_policy()
        document["project_id"] = object()
        with self.assertRaises(ReviewedMotionPolicyValidationError):
            require_reviewed_motion_policy(document)

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
    def test_schema_accepts_valid_and_rejects_structural_mutation(self):
        schema = json.loads(
            (ROOT / "schemas" / "reviewed-motion-policy-v1.schema.json")
            .read_text(encoding="utf-8")
        )
        validator = Draft202012Validator(schema)
        validator.validate(valid_policy(loop=True))
        static_loop = valid_policy(loop=True)
        static_loop["slot_order"]["keys"] = static_loop["slot_order"]["keys"][:1]
        validator.validate(static_loop)
        invalid = valid_policy()
        invalid["root_correction_keys"][0]["extra"] = True
        self.assertTrue(tuple(validator.iter_errors(invalid)))


if __name__ == "__main__":
    unittest.main()
