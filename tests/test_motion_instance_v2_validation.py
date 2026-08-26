"""MotionInstance v2 standalone, exact-binding, and schema tests."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional dependency
    Draft202012Validator = None

from autospine_workbench.motion_instance_validation import (
    MotionInstanceValidationError,
    require_motion_instance,
)
from autospine_workbench.motion_instance_v2_validation import (
    MotionInstanceV2ValidationError,
    motion_instance_v2_sha256,
    require_motion_instance_v2,
)
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.reviewed_motion_policy_validation import (
    reviewed_motion_policy_sha256,
)
from tests.test_motion_instance_contract import instance_fixture, target_fixture
from tests.test_reviewed_motion_policy_validation import valid_policy


ROOT = Path(__file__).resolve().parents[1]
DURATION = 1_000_000


def exact_fixture():
    target = target_fixture()
    base = instance_fixture(target)
    policy = valid_policy(loop=True)
    policy["project_id"] = target["project_id"]
    policy["clip_id"] = base["clip_id"]
    policy["timing"] = {
        **base["timing"],
        "frame_count": 3,
    }
    policy["root_correction_keys"] = [
        {
            "tick": 0, "correction_xy_px": [0.0, 0.0],
            "incoming_interpolation": "linear",
        },
        {
            "tick": DURATION, "correction_xy_px": [0.0, 0.0],
            "incoming_interpolation": "linear",
        },
    ]
    policy["slot_order"]["keys"] = [
        {"tick": 0, "slot_ids": ["body", "arm", "face"]},
        {"tick": DURATION // 2, "slot_ids": ["body", "face", "arm"]},
        {"tick": DURATION, "slot_ids": ["body", "arm", "face"]},
    ]
    policy["source"]["p5"]["target_profile_sha256"] = canonical_sha256(target)
    policy["source"]["p5"]["instance_sha256"] = canonical_sha256(base)
    policy["source"]["p5"]["bundle_sha256"] = "b" * 64
    policy["source"]["p3"] = deepcopy(target["source"]["p3"])
    instance = {
        "format": "autospine-motion-instance",
        "format_version": 2,
        "clip_id": base["clip_id"],
        "timing": deepcopy(base["timing"]),
        "source": {
            "base_motion_instance_sha256": canonical_sha256(base),
            "base_retarget_bundle_sha256": "b" * 64,
            "target_profile_sha256": canonical_sha256(target),
            "reviewed_motion_policy_sha256": reviewed_motion_policy_sha256(policy),
            "motion_policy_decision_sha256": policy["source"][
                "motion_policy_decision_sha256"
            ],
            "p3_rig_sha256": policy["source"]["p3"]["rig_sha256"],
            "p3_bundle_sha256": policy["source"]["p3"]["bundle_sha256"],
        },
        "target_space": {
            **base["target_space"],
            "draw_order": "full-back-to-front-stepped",
        },
        "tracks": deepcopy(base["tracks"]),
        "markers": deepcopy(base["markers"]),
        "draw_order": deepcopy(policy["slot_order"]),
    }
    return instance, target, base, policy


class MotionInstanceV2ValidationTests(unittest.TestCase):
    def setUp(self):
        self.instance, self.target, self.base, self.policy = exact_fixture()

    def assert_invalid(self, mutate):
        document = deepcopy(self.instance)
        mutate(document)
        with self.assertRaises(MotionInstanceV2ValidationError):
            require_motion_instance_v2(document)

    def test_standalone_is_canonical_and_exact_inputs_cross_bind(self):
        require_motion_instance_v2(self.instance)
        require_motion_instance_v2(
            self.instance,
            target_profile=self.target,
            base_motion_instance=self.base,
            reviewed_motion_policy=self.policy,
        )
        reordered = json.loads(json.dumps(self.instance, sort_keys=True))
        self.assertEqual(
            motion_instance_v2_sha256(self.instance),
            motion_instance_v2_sha256(reordered),
        )

    def test_v1_and_v2_validators_are_version_isolated(self):
        with self.assertRaises(MotionInstanceValidationError):
            require_motion_instance(self.instance)
        with self.assertRaises(MotionInstanceV2ValidationError):
            require_motion_instance_v2(self.base)

    def test_unknown_fields_bad_hash_space_and_unsafe_slots_fail_closed(self):
        for mutate in (
            lambda row: row.__setitem__("latest", True),
            lambda row: row["source"].__setitem__("future", "a" * 64),
            lambda row: row["source"].__setitem__(
                "base_motion_instance_sha256", "A" * 64
            ),
            lambda row: row["target_space"].__setitem__("draw_order", "linear"),
            lambda row: row["draw_order"].__setitem__("mode", "stepped"),
            lambda row: row["draw_order"]["setup_slot_ids"].__setitem__(
                0, "unsafe slot/path"
            ),
            lambda row: row["draw_order"]["keys"][0].__setitem__("curve", []),
        ):
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)

    def test_draw_order_requires_ticks_permutations_and_loop_reset(self):
        mutations = (
            lambda row: row["draw_order"]["keys"][0].__setitem__("tick", 1),
            lambda row: row["draw_order"]["keys"][1].__setitem__("tick", 0),
            lambda row: row["draw_order"]["keys"][1].__setitem__(
                "slot_ids", ["body", "arm", "arm"]
            ),
            lambda row: row["draw_order"]["keys"].__setitem__(
                1, deepcopy(row["draw_order"]["keys"][0])
            ),
            lambda row: row["draw_order"]["keys"].pop(),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)

        static = deepcopy(self.instance)
        static["draw_order"]["keys"] = static["draw_order"]["keys"][:1]
        require_motion_instance_v2(static)
        duplicated_static = deepcopy(static)
        duplicated_static["draw_order"]["keys"].append({
            "tick": DURATION,
            "slot_ids": deepcopy(static["draw_order"]["setup_slot_ids"]),
        })
        with self.assertRaises(MotionInstanceV2ValidationError):
            require_motion_instance_v2(duplicated_static)

    def test_exact_base_policy_target_and_draw_order_staleness_is_rejected(self):
        stale_source = deepcopy(self.instance)
        stale_source["source"]["base_motion_instance_sha256"] = "e" * 64
        with self.assertRaisesRegex(MotionInstanceV2ValidationError, "Base"):
            require_motion_instance_v2(
                stale_source, base_motion_instance=self.base
            )

        stale_policy = deepcopy(self.instance)
        stale_policy["source"]["reviewed_motion_policy_sha256"] = "e" * 64
        with self.assertRaisesRegex(MotionInstanceV2ValidationError, "policy"):
            require_motion_instance_v2(
                stale_policy, reviewed_motion_policy=self.policy
            )

        stale_target = deepcopy(self.instance)
        stale_target["source"]["p3_rig_sha256"] = "e" * 64
        with self.assertRaisesRegex(MotionInstanceV2ValidationError, "P3"):
            require_motion_instance_v2(stale_target, target_profile=self.target)

        different_order = deepcopy(self.instance)
        different_order["timing"]["loop"] = False
        different_order["draw_order"]["keys"] = different_order[
            "draw_order"
        ]["keys"][:2]
        changed_policy = deepcopy(self.policy)
        changed_policy["timing"]["loop"] = False
        changed_policy["slot_order"]["keys"] = [
            changed_policy["slot_order"]["keys"][0]
        ]
        changed_policy["root_correction_keys"][-1]["correction_xy_px"] = [1.0, 0.0]
        different_order["source"]["reviewed_motion_policy_sha256"] = (
            reviewed_motion_policy_sha256(changed_policy)
        )
        with self.assertRaisesRegex(MotionInstanceV2ValidationError, "Draw order"):
            require_motion_instance_v2(
                different_order, reviewed_motion_policy=changed_policy
            )

    def test_exact_overlay_rejects_track_or_marker_substitution(self):
        from autospine_workbench.motion_instance_v2_overlay import (
            overlay_motion_tracks,
        )

        compiled = deepcopy(self.instance)
        compiled["tracks"] = overlay_motion_tracks(self.base, self.policy)
        changed = deepcopy(compiled)
        changed["tracks"][0]["keys"][1]["value"] += 1.0
        with self.assertRaisesRegex(
            MotionInstanceV2ValidationError, "exact reviewed overlay"
        ):
            require_motion_instance_v2(
                changed,
                target_profile=self.target,
                base_motion_instance=self.base,
                reviewed_motion_policy=self.policy,
            )
        changed = deepcopy(compiled)
        changed["markers"].pop()
        with self.assertRaisesRegex(
            MotionInstanceV2ValidationError, "exact base"
        ):
            require_motion_instance_v2(
                changed,
                target_profile=self.target,
                base_motion_instance=self.base,
                reviewed_motion_policy=self.policy,
            )

    def test_policy_exact_binding_covers_every_projected_source_address(self):
        fields = (
            "base_motion_instance_sha256", "base_retarget_bundle_sha256",
            "target_profile_sha256", "motion_policy_decision_sha256",
            "p3_rig_sha256", "p3_bundle_sha256",
        )
        for field in fields:
            stale = deepcopy(self.instance)
            stale["source"][field] = "e" * 64
            with self.subTest(field=field), self.assertRaisesRegex(
                MotionInstanceV2ValidationError, "policy source"
            ):
                require_motion_instance_v2(
                    stale, reviewed_motion_policy=self.policy
                )

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
    def test_schema_accepts_fixture_and_rejects_v1_or_unknown_fields(self):
        schema = json.loads(
            (ROOT / "schemas" / "motion-instance-v2.schema.json").read_text("utf-8")
        )
        validator = Draft202012Validator(schema)
        self.assertEqual([], list(validator.iter_errors(self.instance)))
        self.assertNotEqual([], list(validator.iter_errors(self.base)))
        unknown = deepcopy(self.instance)
        unknown["draw_order"]["keys"][0]["curve"] = "linear"
        self.assertNotEqual([], list(validator.iter_errors(unknown)))


if __name__ == "__main__":
    unittest.main()
