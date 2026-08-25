"""Exact built-in MotionIR content, immutability, and determinism tests."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.motion_builtin import (  # noqa: E402
    DURATION,
    BuiltinMotionError,
    build_builtin_motion,
)
from autospine_workbench.motion_validation import (  # noqa: E402
    motion_ir_sha256,
    require_motion_ir,
)


EXPECTED_SHA256 = {
    "idle": "e19e0885420378c51e0a6c9cd775b880bb3708bf793ea4c87d53dce44848f85d",
    "wave.left": "d054364dd9d6118814ba7623e5a0716102bfa8610d3d78dbcdabbe396a82c9d1",
}


class BuiltinMotionTests(unittest.TestCase):
    def test_builtins_are_valid_and_have_fixed_canonical_sha(self):
        for clip_id, expected in EXPECTED_SHA256.items():
            motion = build_builtin_motion(clip_id)
            with self.subTest(clip_id=clip_id):
                require_motion_ir(motion.document)
                self.assertEqual(expected, motion.sha256)
                self.assertEqual(expected, motion_ir_sha256(motion.document))
                self.assertEqual(
                    motion.canonical_json,
                    json.dumps(motion.document, ensure_ascii=False, allow_nan=False,
                               sort_keys=True, separators=(",", ":")),
                )

    def test_document_access_is_deeply_isolated_and_dataclass_is_frozen(self):
        motion = build_builtin_motion("idle")
        first = motion.document
        first["tracks"][0]["keys"][0]["value"] = 99.0
        first["markers"].clear()
        self.assertEqual(0.0, motion.document["tracks"][0]["keys"][0]["value"])
        self.assertEqual(2, len(motion.document["markers"]))
        with self.assertRaises((AttributeError, TypeError)):
            motion._canonical_json = "{}"  # type: ignore[misc]

    def test_idle_has_exact_looping_tracks_and_leg_contacts(self):
        document = build_builtin_motion("idle").document
        self.assertTrue(document["loop"])
        self.assertEqual(DURATION, document["duration_ticks"])
        expected = {
            ("humanoid.head", "rotation"): (
                [0, 500_000, 1_000_000, 1_500_000, 2_000_000],
                [0.0, -1.0, 0.0, 1.0, 0.0],
            ),
            ("humanoid.root", "translation"): (
                [0, 1_000_000, 2_000_000],
                [[0.0, 0.0], [0.0, -0.005], [0.0, 0.0]],
            ),
            ("humanoid.spine.lower", "rotation"): (
                [0, 1_000_000, 2_000_000], [0.0, 0.75, 0.0],
            ),
            ("humanoid.spine.upper", "rotation"): (
                [0, 1_000_000, 2_000_000], [0.0, -1.5, 0.0],
            ),
        }
        self.assertEqual(expected, _track_values(document))
        _assert_leg_contacts(self, document)

    def test_wave_uses_clavicle_rotation_and_ik_without_chain_rotation_conflict(self):
        document = build_builtin_motion("wave.left").document
        self.assertFalse(document["loop"])
        expected = {
            ("humanoid.clavicle.left", "rotation"): (
                [0, 500_000, 1_500_000, 2_000_000], [0.0, -5.0, -5.0, 0.0],
            ),
            ("arm.left", "target"): (
                [0, 400_000, 800_000, 1_200_000, 1_600_000, 2_000_000],
                ["setup", [0.35, 0.65], [0.55, 0.65], [0.35, 0.75],
                 [0.55, 0.65], "setup"],
            ),
        }
        self.assertEqual(expected, _track_values(document))
        rotated = {
            track["target"] for track in document["tracks"]
            if track["property"] == "rotation"
        }
        self.assertTrue(rotated.isdisjoint({
            "humanoid.arm.upper.left", "humanoid.arm.lower.left",
        }))
        _assert_leg_contacts(self, document)

    def test_unknown_ids_fail_closed_and_repeated_builds_are_byte_identical(self):
        for value in ("wave", "wave.right", "IDLE", "", None, True):
            with self.subTest(value=value), self.assertRaises(BuiltinMotionError):
                build_builtin_motion(value)  # type: ignore[arg-type]
        for clip_id in EXPECTED_SHA256:
            first = build_builtin_motion(clip_id)
            second = build_builtin_motion(clip_id)
            self.assertEqual(first, second)
            self.assertEqual(first.canonical_json, second.canonical_json)


def _track_values(document):
    return {
        (track["target"], track["property"]): (
            [key["tick"] for key in track["keys"]],
            [key["value"] for key in track["keys"]],
        )
        for track in document["tracks"]
    }


def _assert_leg_contacts(case, document):
    case.assertEqual([
        {"kind": "contact", "limb": "leg.left", "start_tick": 0,
         "end_tick": DURATION, "mode": "annotation_only"},
        {"kind": "contact", "limb": "leg.right", "start_tick": 0,
         "end_tick": DURATION, "mode": "annotation_only"},
    ], document["markers"])


if __name__ == "__main__":
    unittest.main()
