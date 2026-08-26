"""P7a contract tests for the synthetic Kimodo-shaped SOMA77 fixture."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.bvh_map_validation import (  # noqa: E402
    bvh_map_sha256,
    require_bvh_map,
)
from autospine_workbench.bvh_motion_compiler import (  # noqa: E402
    compile_bvh_motion,
)
from autospine_workbench.bvh_parser import parse_bvh  # noqa: E402
from autospine_workbench.motion_validation import (  # noqa: E402
    require_motion_ir,
)
from tests.fixtures.kimodo_soma77_fixture import (  # noqa: E402
    BVH_JOINT_NAMES,
    JOINT_CHANNELS,
    ROOT_CHANNELS,
    SOMA77_JOINT_NAMES,
    build_soma77_bvh,
    load_soma77_map,
)


EXPECTED_SOURCE_SHA256 = (
    "2536586c39cee7dae0003257d331da620f6da7257adb41fbd19de4c94274745b"
)
EXPECTED_MAP_SHA256 = (
    "c9e4afdc636ad364a577df1831e74b1058a00d75f0876c76c980e1b8eb2cc88e"
)
EXPECTED_MOTION_SHA256 = (
    "229ac23853adf2b7130b72f1815fccb8d2a7fd810ebee29b6aff98e5b60573cc"
)


class KimodoSoma77FixtureTests(unittest.TestCase):
    def test_parse_preserves_double_root_soma77_inventory_and_30hz_samples(self):
        raw = build_soma77_bvh()
        self.assertEqual(raw, build_soma77_bvh())
        self.assertEqual(EXPECTED_SOURCE_SHA256, hashlib.sha256(raw).hexdigest())

        document = parse_bvh(raw)
        self.assertEqual(BVH_JOINT_NAMES, tuple(j.name for j in document.joints))
        self.assertEqual(77, len(SOMA77_JOINT_NAMES))
        self.assertEqual(78, len(document.joints))
        self.assertEqual((2, 240, 480), (
            document.frame_count,
            document.channel_count,
            document.total_sample_count,
        ))
        self.assertAlmostEqual(1 / 30, document.frame_time_seconds)
        self.assertEqual(ROOT_CHANNELS, document.joints[0].channels)
        self.assertEqual(ROOT_CHANNELS, document.joints[1].channels)
        self.assertEqual(0, document.joints[1].parent_index)
        self.assertTrue(all(
            joint.channels == JOINT_CHANNELS for joint in document.joints[2:]
        ))
        self.assertEqual((0.0,) * 6, document.frames[1][:6])
        self.assertEqual(2.0, document.frames[1][6])

    def test_explicit_map_cross_validates_without_joint_or_axis_guessing(self):
        raw, explicit_map = build_soma77_bvh(), load_soma77_map()
        document = parse_bvh(raw)
        require_bvh_map(explicit_map, bvh=document)
        self.assertEqual(EXPECTED_MAP_SHA256, bvh_map_sha256(explicit_map))
        self.assertEqual("kimodo.soma77.front-v1", explicit_map["map_id"])
        self.assertEqual("kimodo.soma77.smoke.front", explicit_map["clip"]["clip_id"])
        self.assertEqual(("+X", "-Y", "+Z"), tuple(
            explicit_map["basis"][key] for key in ("screen_x", "screen_y", "depth")
        ))
        self.assertEqual(15, len(explicit_map["bones"]))

        explicit_map["clip"]["clip_id"] = "mutated"
        self.assertEqual(
            "kimodo.soma77.smoke.front",
            load_soma77_map()["clip"]["clip_id"],
        )

    def test_compile_is_canonical_and_retains_hips_root_motion(self):
        first = compile_bvh_motion(build_soma77_bvh(), load_soma77_map())
        second = compile_bvh_motion(build_soma77_bvh(), load_soma77_map())
        self.assertEqual(first.canonical_bytes, second.canonical_bytes)
        self.assertEqual(EXPECTED_MOTION_SHA256, first.sha256)

        motion = first.document
        require_motion_ir(motion)
        self.assertEqual("kimodo.soma77.smoke.front", motion["clip_id"])
        self.assertEqual(33_333, motion["duration_ticks"])
        self.assertFalse(motion["loop"])
        self.assertEqual(16, len(motion["tracks"]))
        root_translation = next(
            track for track in motion["tracks"]
            if track["target"] == "humanoid.root"
            and track["property"] == "translation"
        )
        self.assertEqual([[0.0, 0.0], [0.02, 0.0]], [
            key["value"] for key in root_translation["keys"]
        ])
        rotations = {
            track["target"]: [key["value"] for key in track["keys"]]
            for track in motion["tracks"] if track["property"] == "rotation"
        }
        self.assertEqual([0.0, -10.0], rotations["humanoid.root"])
        self.assertEqual([0.0, 0.0], rotations["humanoid.leg.upper.left"])
        self.assertEqual([0.0, 0.0], rotations["humanoid.leg.upper.right"])
        self.assertEqual([], motion["markers"])


if __name__ == "__main__":
    unittest.main()
