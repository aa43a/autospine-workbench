"""MotionIR v1 schema, semantic, determinism, and resource tests."""

from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.motion_roles import (  # noqa: E402
    CANONICAL_BONE_ROLES,
    CANONICAL_IK_HANDLES,
)
from autospine_workbench.motion_validation import (  # noqa: E402
    MotionValidationError,
    TICKS_PER_SECOND,
    motion_coordinate_system,
    motion_ir_sha256,
    require_motion_ir,
)

try:
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError
except ImportError:  # pragma: no cover - optional test extra
    Draft202012Validator = None
    ValidationError = Exception


DURATION = TICKS_PER_SECOND


def motion_fixture(*, loop=False):
    rotation = [
        {"tick": 0, "value": 350.0},
        {"tick": DURATION, "value": 370.0},
    ]
    translation = [
        {"tick": 0, "value": [0.0, 0.0]},
        {"tick": DURATION, "value": [0.1, -0.05]},
    ]
    target = [
        {"tick": 0, "value": "setup"},
        {"tick": DURATION, "value": [0.75, 0.2]},
    ]
    if loop:
        rotation.insert(1, {"tick": DURATION // 2, "value": 370.0})
        rotation[-1]["value"] = 350.0
        translation.insert(1, {"tick": DURATION // 2, "value": [0.1, -0.05]})
        translation[-1]["value"] = [0.0, 0.0]
        target.insert(1, {"tick": DURATION // 2, "value": [0.75, 0.2]})
        target[-1]["value"] = "setup"
    return {
        "format": "autospine-motion-ir",
        "format_version": 1,
        "clip_id": "wave-v1",
        "ticks_per_second": TICKS_PER_SECOND,
        "duration_ticks": DURATION,
        "loop": loop,
        "coordinate_system": motion_coordinate_system(),
        "tracks": [
            {
                "target_kind": "bone_role",
                "target": "humanoid.clavicle.left",
                "property": "rotation",
                "interpolation": "linear",
                "keys": rotation,
            },
            {
                "target_kind": "bone_role",
                "target": "humanoid.root",
                "property": "translation",
                "interpolation": "linear",
                "keys": translation,
            },
            {
                "target_kind": "ik_handle",
                "target": "arm.left",
                "property": "target",
                "interpolation": "linear",
                "keys": target,
            },
        ],
        "markers": [
            {"kind": "contact", "limb": "arm.left", "start_tick": 100,
             "end_tick": 200, "mode": "annotation_only"},
            {"kind": "contact", "limb": "leg.left", "start_tick": 300,
             "end_tick": DURATION, "mode": "annotation_only"},
        ],
    }


def reverse_keys(value):
    if isinstance(value, dict):
        return {key: reverse_keys(item) for key, item in reversed(list(value.items()))}
    if isinstance(value, list):
        return [reverse_keys(item) for item in value]
    return value


class MotionIrSchemaTests(unittest.TestCase):
    def schema(self):
        return json.loads((ROOT / "schemas" / "motion-ir-v1.schema.json").read_text())

    def test_schema_is_strict_draft_2020_12_and_pins_role_inventories(self):
        schema = self.schema()
        self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
        self.assertEqual(set(CANONICAL_BONE_ROLES), set(schema["$defs"]["boneRole"]["enum"]))
        self.assertEqual(set(CANONICAL_IK_HANDLES), set(schema["$defs"]["ikHandle"]["enum"]))
        if Draft202012Validator is None:
            return
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        validator.validate(motion_fixture())
        validator.validate(motion_fixture(loop=True))

    @unittest.skipIf(Draft202012Validator is None, "install the test extra")
    def test_schema_rejects_unknown_fields_forbidden_tracks_and_root_setup_sentinel(self):
        validator = Draft202012Validator(self.schema())
        mutations = (
            lambda value: value.update(slots=[]),
            lambda value: value["tracks"][0].update(property="scale"),
            lambda value: value["tracks"][1]["keys"][0].update(value="setup"),
            lambda value: value["markers"][0].update(mode="runtime_event"),
        )
        for mutate in mutations:
            value = motion_fixture()
            mutate(value)
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validator.validate(value)


class MotionIrValidationTests(unittest.TestCase):
    def test_valid_clip_is_non_mutating_and_canonical_sha_ignores_object_key_order(self):
        clip = motion_fixture(loop=True)
        before = deepcopy(clip)
        first = motion_ir_sha256(clip)
        second = motion_ir_sha256(reverse_keys(clip))
        self.assertEqual(first, second)
        self.assertEqual(before, clip)
        require_motion_ir(clip)
        self.assertEqual("down", clip["coordinate_system"]["y_axis"])
        self.assertEqual("clockwise", clip["coordinate_system"]["positive_rotation"])
        self.assertEqual("setup_local_additive", clip["coordinate_system"]["rotation_space"])
        self.assertEqual("half_open", clip["coordinate_system"]["contact_interval"])

    def test_continuous_unwrapped_angles_are_preserved_and_wrapped_jump_is_rejected(self):
        continuous = motion_fixture()
        continuous["tracks"][0]["keys"] = [
            {"tick": 0, "value": 179.0},
            {"tick": DURATION, "value": 181.0},
        ]
        require_motion_ir(continuous)
        unwrapped_sha = motion_ir_sha256(continuous)
        self.assertEqual(181.0, continuous["tracks"][0]["keys"][-1]["value"])
        normalized = deepcopy(continuous)
        normalized["tracks"][0]["keys"] = [
            {"tick": 0, "value": -1.0},
            {"tick": DURATION, "value": 1.0},
        ]
        self.assertNotEqual(unwrapped_sha, motion_ir_sha256(normalized))
        wrapped = deepcopy(continuous)
        wrapped["tracks"][0]["keys"][-1]["value"] = -179.0
        with self.assertRaisesRegex(MotionValidationError, "wrapped angle jump"):
            require_motion_ir(wrapped)

    def test_track_targets_properties_and_interpolation_are_fail_closed(self):
        mutations = (
            lambda value: value["tracks"][0].update(target="unknown.role"),
            lambda value: value["tracks"][1].update(target="humanoid.head"),
            lambda value: value["tracks"][2].update(target="hand.left"),
            lambda value: value["tracks"][2].update(property="rotation"),
            lambda value: value["tracks"][0].update(interpolation="step"),
        )
        for mutate in mutations:
            value = motion_fixture()
            mutate(value)
            with self.subTest(value=value), self.assertRaises(MotionValidationError):
                require_motion_ir(value)

    def test_ik_chain_rotations_cannot_compete_with_the_same_handle(self):
        conflicts = (
            "humanoid.arm.upper.left",
            "humanoid.arm.lower.left",
        )
        for role in conflicts:
            value = motion_fixture()
            value["tracks"][0]["target"] = role
            with self.subTest(role=role), self.assertRaisesRegex(
                MotionValidationError, "IK chain"
            ):
                require_motion_ir(value)
        allowed = motion_fixture()
        allowed["tracks"][0]["target"] = "humanoid.arm.upper.right"
        require_motion_ir(allowed)
        for forbidden in ("scale", "deform", "draw_order", "slot", "skin"):
            value = motion_fixture()
            value["tracks"][0]["property"] = forbidden
            with self.subTest(forbidden=forbidden), self.assertRaises(MotionValidationError):
                require_motion_ir(value)

    def test_format_version_and_tick_rate_require_exact_integers(self):
        for field, value in (
            ("format_version", 1.0),
            ("format_version", True),
            ("ticks_per_second", float(TICKS_PER_SECOND)),
            ("ticks_per_second", True),
        ):
            clip = motion_fixture()
            clip[field] = value
            with self.subTest(field=field, value=value), \
                    self.assertRaises(MotionValidationError):
                require_motion_ir(clip)

    def test_ticks_endpoints_track_order_and_loop_endpoints_are_strict(self):
        mutations = (
            lambda value: value["tracks"][0]["keys"][0].update(tick=1),
            lambda value: value["tracks"][0]["keys"][1].update(tick=1.5),
            lambda value: value["tracks"][0]["keys"].reverse(),
            lambda value: value["tracks"].reverse(),
            lambda value: value["tracks"].append(deepcopy(value["tracks"][-1])),
        )
        for mutate in mutations:
            value = motion_fixture()
            mutate(value)
            with self.subTest(value=value), self.assertRaises(MotionValidationError):
                require_motion_ir(value)
        loop = motion_fixture(loop=True)
        loop["tracks"][0]["keys"][-1]["value"] += 1
        with self.assertRaisesRegex(MotionValidationError, "endpoints"):
            require_motion_ir(loop)

    def test_setup_sentinel_is_ik_only_and_coordinate_semantics_are_pinned(self):
        require_motion_ir(motion_fixture(loop=True))
        root_setup = motion_fixture()
        root_setup["tracks"][1]["keys"][0]["value"] = "setup"
        with self.assertRaises(MotionValidationError):
            require_motion_ir(root_setup)
        for field in (
            "root_translation_space", "ik_target_space", "ik_unreachable_policy",
        ):
            value = motion_fixture()
            value["coordinate_system"][field] = "unsupported"
            with self.subTest(field=field), self.assertRaises(MotionValidationError):
                require_motion_ir(value)

    def test_contact_markers_are_sorted_half_open_annotation_only_intervals(self):
        touching = motion_fixture()
        touching["markers"] = [
            {"kind": "contact", "limb": "leg.left", "start_tick": 100,
             "end_tick": 200, "mode": "annotation_only"},
            {"kind": "contact", "limb": "leg.left", "start_tick": 200,
             "end_tick": DURATION, "mode": "annotation_only"},
        ]
        require_motion_ir(touching)
        mutations = (
            lambda value: value["markers"][0].update(kind="event"),
            lambda value: value["markers"][0].update(limb="torso"),
            lambda value: value["markers"][0].update(mode="runtime"),
            lambda value: value["markers"][0].update(end_tick=100),
            lambda value: value["markers"].reverse(),
        )
        for mutate in mutations:
            value = motion_fixture()
            mutate(value)
            with self.subTest(value=value), self.assertRaises(MotionValidationError):
                require_motion_ir(value)
        overlap = motion_fixture()
        overlap["markers"] = [
            {"kind": "contact", "limb": "arm.left", "start_tick": 100,
             "end_tick": 300, "mode": "annotation_only"},
            {"kind": "contact", "limb": "arm.left", "start_tick": 200,
             "end_tick": 400, "mode": "annotation_only"},
        ]
        with self.assertRaisesRegex(MotionValidationError, "overlap"):
            require_motion_ir(overlap)

    def test_unknown_fields_nonfinite_and_bounded_values_fail_closed(self):
        for location in ("top", "track", "key", "marker"):
            value = motion_fixture()
            target = value if location == "top" else (
                value["tracks"][0] if location == "track" else
                value["tracks"][0]["keys"][0] if location == "key" else
                value["markers"][0]
            )
            target["unknown"] = True
            with self.subTest(location=location), self.assertRaises(MotionValidationError):
                require_motion_ir(value)
        for number in (math.nan, math.inf, -math.inf):
            value = motion_fixture()
            value["tracks"][0]["keys"][0]["value"] = number
            with self.subTest(number=number), self.assertRaises(MotionValidationError):
                require_motion_ir(value)
        value = motion_fixture()
        value["tracks"][1]["keys"][0]["value"] = [1025.0, 0.0]
        with self.assertRaises(MotionValidationError):
            require_motion_ir(value)

    def test_resource_caps_are_enforced_before_canonical_publication(self):
        from autospine_workbench import motion_validation as module
        cases = (
            ("MAX_TRACKS", 2), ("MAX_TOTAL_KEYS", 5), ("MAX_MARKERS", 1),
            ("MAX_DOCUMENT_BYTES", 1),
        )
        for name, limit in cases:
            with self.subTest(name=name), patch.object(module, name, limit), \
                    self.assertRaises(MotionValidationError):
                require_motion_ir(motion_fixture())
        value = motion_fixture()
        value["duration_ticks"] = module.MAX_DURATION_TICKS + 1
        for track in value["tracks"]:
            track["keys"][-1]["tick"] = value["duration_ticks"]
        with self.assertRaises(MotionValidationError):
            motion_ir_sha256(value)


if __name__ == "__main__":
    unittest.main()
