"""Pure BVH-to-MotionIR compiler contract and regression tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.bvh_motion_compiler import (  # noqa: E402
    CONTACT_PROFILE,
    CONTACT_INTERVAL_PROFILE,
    CONTACT_VELOCITY_PROFILE,
    DECIMAL_PLACES,
    FK_PROFILE,
    PROJECTION_PROFILE,
    ROTATION_PROFILE,
    LOOP_PROFILE,
    TICK_PROFILE,
    BvhMotionCompilerError,
    bvh_motion_compiler_config,
    compile_bvh_motion,
)
from autospine_workbench.bvh_fk import project_bvh_frames  # noqa: E402
from autospine_workbench.bvh_parser import parse_bvh  # noqa: E402
from autospine_workbench.motion_validation import (  # noqa: E402
    TICKS_PER_SECOND,
    motion_ir_sha256,
    require_motion_ir,
)


RAW = b"""HIERARCHY
ROOT Hips
{
 OFFSET 0 0 0
 CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
 JOINT LeftUpLeg
 {
  OFFSET 1 0 0
  CHANNELS 3 Zrotation Xrotation Yrotation
  JOINT LeftLeg
  {
   OFFSET 0 10 0
   CHANNELS 3 Zrotation Xrotation Yrotation
   JOINT LeftFoot
   {
    OFFSET 0 10 0
    CHANNELS 3 Zrotation Xrotation Yrotation
    End Site { OFFSET 0 2 0 }
   }
  }
 }
}
MOTION
Frames: 3
Frame Time: 0.5
0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
1 2 0 10 0 0 20 0 0 -5 0 0 0 0 0
2 4 0 20 0 0 40 0 0 -10 0 0 0 0 0
"""


def bone(role, joint, aim):
    return {
        "role": role,
        "joint_name": joint,
        "aim": {"kind": "joint", "joint_name": aim},
        "rotation_policy": "projected_setup_local_delta",
    }


def mapping():
    return {
        "format": "autospine-bvh-map",
        "format_version": 1,
        "map_id": "test.front-v1",
        "clip": {"clip_id": "stride.front", "loop": False},
        "basis": {
            "screen_x": "+X",
            "screen_y": "+Y",
            "depth": "+Z",
            "rotation_convention": "bvh_declared_channel_postmultiply",
        },
        "root": {
            "joint_name": "Hips",
            "reference_length_source_units": 10.0,
            "translation_policy":
                "projected_frame0_delta_normalized_reference_length",
        },
        "bones": [
            bone("humanoid.root", "Hips", "LeftUpLeg"),
            bone("humanoid.leg.upper.left", "LeftUpLeg", "LeftLeg"),
            bone("humanoid.leg.lower.left", "LeftLeg", "LeftFoot"),
        ],
        "contact": {
            "enabled": True,
            "feet": [{"limb": "leg.left", "foot_joint_name": "LeftFoot"}],
            "floor_height_source_units": 0.0,
            "height_threshold_source_units": 1000.0,
            "speed_threshold_source_units_per_second": 1_000_000.0,
            "minimum_frames": 1,
            "gap_frames": 0,
            "height_policy":
                "absolute_signed_basis_screen_y_distance_to_floor",
            "speed_policy": "source_world_3d_euclidean",
            "mode": "annotation_only",
            "interval": "half_open",
        },
    }


def reverse_objects(value):
    if isinstance(value, dict):
        return {key: reverse_objects(item) for key, item in reversed(list(value.items()))}
    if isinstance(value, list):
        return [reverse_objects(item) for item in value]
    return value


class BvhMotionCompilerSuccessTests(unittest.TestCase):
    def test_compiles_exact_setup_local_tracks_root_motion_and_contacts(self):
        compiled = compile_bvh_motion(RAW, mapping())
        document = compiled.document
        require_motion_ir(document)
        self.assertEqual("stride.front", document["clip_id"])
        self.assertEqual(TICKS_PER_SECOND, document["duration_ticks"])
        self.assertFalse(document["loop"])
        identities = [
            (track["target"], track["property"])
            for track in document["tracks"]
        ]
        self.assertEqual([
            ("humanoid.leg.lower.left", "rotation"),
            ("humanoid.leg.upper.left", "rotation"),
            ("humanoid.root", "rotation"),
            ("humanoid.root", "translation"),
        ], identities)
        values = {
            (track["target"], track["property"]):
                [key["value"] for key in track["keys"]]
            for track in document["tracks"]
        }
        self.assertEqual([0.0, -5.0, -10.0], values[
            ("humanoid.leg.lower.left", "rotation")
        ])
        self.assertEqual([0.0, 20.0, 40.0], values[
            ("humanoid.leg.upper.left", "rotation")
        ])
        self.assertEqual([0.0, 10.0, 20.0], values[
            ("humanoid.root", "rotation")
        ])
        self.assertEqual([[0.0, 0.0], [0.1, 0.2], [0.2, 0.4]], values[
            ("humanoid.root", "translation")
        ])
        self.assertEqual([{
            "kind": "contact", "limb": "leg.left", "start_tick": 0,
            "end_tick": TICKS_PER_SECOND, "mode": "annotation_only",
        }], document["markers"])

    def test_result_is_deterministic_canonical_frozen_and_non_mutating(self):
        value = mapping()
        before = deepcopy(value)
        first = compile_bvh_motion(RAW, value)
        second = compile_bvh_motion(RAW, reverse_objects(value))
        self.assertEqual(before, value)
        self.assertEqual(first.canonical_bytes, second.canonical_bytes)
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(hashlib.sha256(first.canonical_bytes).hexdigest(), first.sha256)
        self.assertEqual(motion_ir_sha256(first.document), first.sha256)
        changed = first.document
        changed["tracks"].clear()
        self.assertNotEqual(changed, first.document)
        self.assertEqual(
            first.canonical_json,
            json.dumps(first.document, sort_keys=True, separators=(",", ":")),
        )

    def test_compiler_profile_is_exact_and_returns_fresh_config(self):
        expected = {
            "fk": FK_PROFILE,
            "projection": PROJECTION_PROFILE,
            "rotation": ROTATION_PROFILE,
            "contact": CONTACT_PROFILE,
            "contact_velocity": CONTACT_VELOCITY_PROFILE,
            "contact_intervals": CONTACT_INTERVAL_PROFILE,
            "tick_schedule": TICK_PROFILE,
            "loop_closure": LOOP_PROFILE,
            "ticks_per_second": TICKS_PER_SECOND,
            "decimal_places": DECIMAL_PLACES,
        }
        first = bvh_motion_compiler_config()
        self.assertEqual(expected, first)
        first["fk"] = "changed"
        self.assertEqual(expected, bvh_motion_compiler_config())


class BvhMotionCompilerRejectionTests(unittest.TestCase):
    def test_malformed_nonimmutable_and_guessing_inputs_fail_closed(self):
        guessed = mapping()
        guessed["basis"]["guessed_up"] = True
        for raw, value in ((b"", mapping()), (bytearray(RAW), mapping()), (RAW, guessed)):
            with self.subTest(raw_type=type(raw), value=value), self.assertRaises(
                BvhMotionCompilerError
            ):
                compile_bvh_motion(raw, value)  # type: ignore[arg-type]

    def test_loop_endpoint_drift_is_rejected_not_silently_closed(self):
        value = mapping()
        value["clip"]["loop"] = True
        with self.assertRaisesRegex(BvhMotionCompilerError, "endpoints differ"):
            compile_bvh_motion(RAW, value)

    def test_contact_evidence_cannot_mix_another_projection_identity(self):
        projected = project_bvh_frames(parse_bvh(RAW), mapping())
        mixed = replace(projected, map_sha256="0" * 64)
        with patch(
            "autospine_workbench.bvh_motion_compiler.project_bvh_frames",
            return_value=mixed,
        ), self.assertRaisesRegex(BvhMotionCompilerError, "identity"):
            compile_bvh_motion(RAW, mapping())

    def test_motion_ir_key_resource_boundary_is_enforced(self):
        with patch(
            "autospine_workbench.motion_validation.MAX_KEYS_PER_TRACK", 2
        ), self.assertRaisesRegex(BvhMotionCompilerError, "key resource"):
            compile_bvh_motion(RAW, mapping())


if __name__ == "__main__":
    unittest.main()
