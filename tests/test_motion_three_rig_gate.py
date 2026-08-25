"""P5 gate: the same reusable clips must pass three distinct setup rigs."""

from __future__ import annotations

import math
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.motion_bundle_reader import (  # noqa: E402
    VerifiedMotionBundleReader,
)
from autospine_workbench.motion_bundle_store import MotionBundleStore  # noqa: E402
from autospine_workbench.motion_instance_sampling import (  # noqa: E402
    instance_sample_ticks,
    sample_instance_pose,
)
from autospine_workbench.motion_retarget_compiler import (  # noqa: E402
    compile_motion_instance,
)
from autospine_workbench.motion_target_profile import (  # noqa: E402
    compile_motion_target_profile,
)
from tests.test_motion_bundle_contract import payload  # noqa: E402
from tests.test_motion_target_profile import full_rig, pair  # noqa: E402


ASYMMETRIC_SETUP = {
    "root-pelvis": (173, 421, -83, 24),
    "pelvis-spine": (24, 0, 4, 63),
    "spine-chest": (63, 0, -7, 77),
    "chest-neck": (77, 0, 6, 23),
    "neck-head": (23, 0, -9, 31),
    "chest-shoulder.left": (77, 0, 94, 42),
    "upper-arm.left": (42, 0, 37, 51),
    "forearm.left": (51, 0, -48, 39),
    "chest-shoulder.right": (77, 0, -86, 35),
    "upper-arm.right": (35, 0, -31, 62),
    "forearm.right": (62, 0, 44, 47),
    "pelvis-hip.left": (24, 0, 101, 18),
    "thigh.left": (18, 0, 64, 71),
    "calf.left": (71, 0, -23, 54),
    "pelvis-hip.right": (24, 0, -94, 22),
    "thigh.right": (22, 0, -97, 67),
    "calf.right": (67, 0, 31, 61),
}


def rig_from_setup(values, *, x_offset=0):
    rig = full_rig()
    for bone in rig["bones"]:
        x, y, rotation, length = values[bone["id"]]
        if bone["id"] == "root-pelvis":
            x += x_offset
        bone["setup"].update(
            x=x, y=y, rotation_deg=rotation, length=length
        )
    return rig


def tall_asymmetric_rig():
    values = dict(ASYMMETRIC_SETUP)
    lengths = {
        "root-pelvis": 29, "pelvis-spine": 78, "spine-chest": 91,
        "chest-neck": 28, "neck-head": 37,
        "chest-shoulder.left": 49, "upper-arm.left": 58,
        "forearm.left": 46, "chest-shoulder.right": 39,
        "upper-arm.right": 70, "forearm.right": 52,
        "pelvis-hip.left": 21, "thigh.left": 83, "calf.left": 63,
        "pelvis-hip.right": 26, "thigh.right": 75, "calf.right": 69,
    }
    for bone_id, length in lengths.items():
        x, y, rotation, _old = values[bone_id]
        values[bone_id] = x, y, rotation + (2 if ".left" in bone_id else -1), length
    parents = {
        "pelvis-spine": "root-pelvis", "spine-chest": "pelvis-spine",
        "chest-neck": "spine-chest", "neck-head": "chest-neck",
        "chest-shoulder.left": "spine-chest", "upper-arm.left": "chest-shoulder.left",
        "forearm.left": "upper-arm.left", "chest-shoulder.right": "spine-chest",
        "upper-arm.right": "chest-shoulder.right", "forearm.right": "upper-arm.right",
        "pelvis-hip.left": "root-pelvis", "thigh.left": "pelvis-hip.left",
        "calf.left": "thigh.left", "pelvis-hip.right": "root-pelvis",
        "thigh.right": "pelvis-hip.right", "calf.right": "thigh.right",
    }
    for bone_id, parent in parents.items():
        _x, y, rotation, length = values[bone_id]
        values[bone_id] = lengths[parent], y, rotation, length
    return rig_from_setup(values, x_offset=61)


class MotionThreeRigGateTests(unittest.TestCase):
    def test_idle_and_wave_pass_three_distinct_full_setup_rigs(self):
        profiles = [
            compile_motion_target_profile(*pair()),
            compile_motion_target_profile(*pair(
                rig=rig_from_setup(ASYMMETRIC_SETUP)
            )),
            compile_motion_target_profile(*pair(rig=tall_asymmetric_rig())),
        ]
        self.assertEqual(3, len({item.sha256 for item in profiles}))
        asymmetric = profiles[1].document
        self.assertEqual(17, len(asymmetric["bones"]))
        self.assertTrue(all(
            row["setup_local"]["rotation_deg"] != 0
            for row in asymmetric["bones"]
        ))
        self.assertNotEqual(
            asymmetric["ik_handles"][0]["proximal_length_px"],
            asymmetric["ik_handles"][1]["proximal_length_px"],
        )

        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary) / "state"
            results = {}
            for clip_id in ("idle", "wave.left"):
                published = MotionBundleStore(state).publish(*payload(clip_id))
                motion = VerifiedMotionBundleReader(state).load(
                    published.clip_sha256, published.bundle_sha256
                )
                rows = [
                    compile_motion_instance(motion, profile)
                    for profile in profiles
                ]
                results[clip_id] = rows
                self.assertEqual(1, len({
                    row.instance["source"]["motion_bundle_sha256"]
                    for row in rows
                }))
                self.assertEqual(3, len({row.instance_sha256 for row in rows}))
                self.assertEqual(3, len({row.run_identity_sha256 for row in rows}))
                for row, profile in zip(rows, profiles):
                    instance = row.instance
                    self.assertEqual(2, len(instance["markers"]))
                    for tick in instance_sample_ticks(
                        instance, target_profile=profile.document
                    ):
                        pose = sample_instance_pose(
                            instance, target_profile=profile.document, tick=tick
                        )
                        self.assertTrue(all(
                            math.isfinite(number)
                            for bone in pose.values()
                            for field in ("origin_xy", "endpoint_xy")
                            for number in bone[field]
                        ))
            self.assertNotEqual(
                results["idle"][0].instance_sha256,
                results["wave.left"][0].instance_sha256,
            )


if __name__ == "__main__":
    unittest.main()
