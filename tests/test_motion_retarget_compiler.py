"""Pure verified MotionIR-to-MotionInstance compiler tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.motion_bundle_reader import (  # noqa: E402
    VerifiedMotionBundleReader,
)
from autospine_workbench.motion_bundle_store import MotionBundleStore  # noqa: E402
from autospine_workbench.motion_instance_validation import (  # noqa: E402
    require_motion_instance,
)
from autospine_workbench.motion_retarget_compiler import (  # noqa: E402
    MotionRetargetCompilerError,
    compile_motion_instance,
)
from autospine_workbench.motion_retarget_kinematics import (  # noqa: E402
    solve_motion_ik_track,
)
from autospine_workbench.motion_retarget_run import (  # noqa: E402
    require_retarget_run,
)
from autospine_workbench.motion_target_profile import (  # noqa: E402
    compile_motion_target_profile,
)
from tests.test_motion_bundle_contract import payload  # noqa: E402
from tests.test_motion_target_profile import full_rig, pair  # noqa: E402


def encode(value):
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )


class MotionRetargetCompilerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.state = Path(self.temporary.name) / "state"
        self.profile = compile_motion_target_profile(*pair())

    def verified(self, clip_id):
        published = MotionBundleStore(self.state).publish(*payload(clip_id))
        return VerifiedMotionBundleReader(self.state).load(
            published.clip_sha256, published.bundle_sha256
        )

    def test_idle_maps_roles_scales_root_and_binds_exact_provenance(self):
        verified = self.verified("idle")
        result = compile_motion_instance(verified, self.profile)
        instance, run = result.instance, result.run

        require_motion_instance(instance, target_profile=self.profile.document)
        require_retarget_run(run, instance=instance)
        self.assertEqual(verified.clip_sha256, instance["source"]["motion_ir_sha256"])
        self.assertEqual(verified.bundle_sha256,
                         instance["source"]["motion_bundle_sha256"])
        self.assertEqual(verified.run_sha256, instance["source"]["motion_run_sha256"])
        self.assertEqual(self.profile.sha256, result.target_profile_sha)
        self.assertEqual(run["output"]["instance_sha256"], result.instance_sha256)
        self.assertEqual(run["run_identity_sha256"], result.run_identity_sha256)
        self.assertEqual(sorted(
            (track["bone_id"], track["property"]) for track in instance["tracks"]
        ), [(track["bone_id"], track["property"]) for track in instance["tracks"]])
        root = next(track for track in instance["tracks"]
                    if track["property"] == "translation")
        self.assertEqual([0.0, -0.5], root["keys"][1]["value"])
        self.assertEqual(
            ["neck-head", "pelvis-spine", "root-pelvis", "spine-chest"],
            sorted(track["bone_id"] for track in instance["tracks"]),
        )
        self.assertEqual([
            ("leg.left", "thigh.left", "calf.left"),
            ("leg.right", "thigh.right", "calf.right"),
        ], [(item["limb"], item["proximal_bone_id"], item["distal_bone_id"])
            for item in instance["markers"]])

    def test_wave_bakes_reachable_ik_and_setup_endpoints(self):
        verified = self.verified("wave.left")
        result = compile_motion_instance(verified, self.profile)
        instance = result.instance
        self.assertNotIn("ik_handle", encode(instance))
        self.assertEqual(
            ["chest-shoulder.left", "forearm.left", "upper-arm.left"],
            [track["bone_id"] for track in instance["tracks"]],
        )
        for bone_id in ("upper-arm.left", "forearm.left"):
            track = next(item for item in instance["tracks"]
                         if item["bone_id"] == bone_id)
            self.assertEqual(0.0, track["keys"][0]["value"])
            self.assertEqual(0.0, track["keys"][-1]["value"])
            self.assertEqual(
                [0, 400_000, 800_000, 1_200_000, 1_600_000, 2_000_000],
                [key["tick"] for key in track["keys"]],
            )

    def test_determinism_and_two_distinct_target_profiles(self):
        verified = self.verified("wave.left")
        first = compile_motion_instance(verified, self.profile)
        self.assertEqual(first, compile_motion_instance(verified, self.profile))

        shifted = full_rig()
        shifted["bones"][0]["setup"]["x"] += 17
        second_profile = compile_motion_target_profile(*pair(rig=shifted))
        second = compile_motion_instance(verified, second_profile)
        self.assertNotEqual(first.target_profile_sha, second.target_profile_sha)
        self.assertNotEqual(first.run_identity_sha256, second.run_identity_sha256)
        self.assertNotEqual(first.instance_sha256, second.instance_sha256)
        require_motion_instance(second.instance, target_profile=second_profile.document)

    def test_unreachable_and_competing_generated_tracks_are_rejected(self):
        verified = self.verified("wave.left")
        solved = solve_motion_ik_track(
            verified.motion, self.profile.document, "arm.left"
        )
        unreachable = replace(
            solved,
            samples=(replace(solved.samples[0], reach_state="unreachable_too_far"),
                     *solved.samples[1:]),
        )
        with patch(
            "autospine_workbench.motion_retarget_compiler.solve_motion_ik_track",
            return_value=unreachable,
        ), self.assertRaisesRegex(MotionRetargetCompilerError, "unreachable"):
            compile_motion_instance(verified, self.profile)

        competing = replace(solved, proximal_bone_id="chest-shoulder.left")
        with patch(
            "autospine_workbench.motion_retarget_compiler.solve_motion_ik_track",
            return_value=competing,
        ), self.assertRaisesRegex(MotionRetargetCompilerError, "competing"):
            compile_motion_instance(verified, self.profile)

    def test_replaced_or_tampered_verified_inputs_fail_closed(self):
        verified = self.verified("idle")
        with self.assertRaisesRegex(MotionRetargetCompilerError, "identities"):
            compile_motion_instance(
                replace(verified, run_sha256="f" * 64), self.profile
            )

        items = list(verified._document_items)
        changed = deepcopy(verified.motion)
        changed["tracks"][0]["keys"][1]["value"] = -2.0
        items[0] = (items[0][0], encode(changed).encode("utf-8"))
        with self.assertRaises(MotionRetargetCompilerError):
            compile_motion_instance(
                replace(verified, _document_items=tuple(items)), self.profile
            )

        noncanonical = replace(
            self.profile, _document_json=self.profile._document_json + " "
        )
        with self.assertRaisesRegex(MotionRetargetCompilerError, "canonical"):
            compile_motion_instance(verified, noncanonical)

        invalid = self.profile.document
        invalid["body_frame"]["up_xy"] = [1.0, 0.0]
        with self.assertRaises(MotionRetargetCompilerError):
            compile_motion_instance(
                verified, replace(self.profile, _document_json=encode(invalid))
            )

    def test_algorithm_identity_drift_changes_run_identity(self):
        verified = self.verified("idle")
        baseline = compile_motion_instance(verified, self.profile)
        with patch(
            "autospine_workbench.motion_retarget_run.COMPILER_VERSION", "1.0.1"
        ):
            drifted = compile_motion_instance(verified, self.profile)
            require_retarget_run(drifted.run, instance=drifted.instance)
            self.assertEqual("1.0.1", drifted.run["compiler"]["version"])
        self.assertNotEqual(
            baseline.run_identity_sha256, drifted.run_identity_sha256
        )

    def test_inputs_remain_unchanged_and_result_is_frozen_and_isolated(self):
        verified = self.verified("idle")
        before_motion = deepcopy(verified.motion)
        before_target = deepcopy(self.profile.document)
        result = compile_motion_instance(verified, self.profile)
        self.assertEqual(before_motion, verified.motion)
        self.assertEqual(before_target, self.profile.document)

        changed_instance, changed_run = result.instance, result.run
        changed_instance["tracks"].clear()
        changed_run["inputs"].clear()
        self.assertTrue(result.instance["tracks"])
        self.assertTrue(result.run["inputs"])
        with self.assertRaises(FrozenInstanceError):
            result._instance_json = "{}"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
