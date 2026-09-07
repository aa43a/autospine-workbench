"""Canonical parent transforms reconstruct explicit candidate geometry."""
from copy import deepcopy
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.asset.joints.skeleton import LIMBS, build_canonical_skeleton, validate_canonical_skeleton


def fixture():
    candidate = {"schema": "autospine.benchmark-semantic-candidates/v1", "authority": "none", "canvas": [400, 600]}
    xy = {"shoulder": (130, 270, 180), "elbow": (100, 300, 260), "wrist": (80, 320, 340),
          "hip": (160, 240, 320), "knee": (160, 240, 420), "ankle": (160, 240, 520)}
    joints = []
    for joint in LIMBS:
        kind, side = joint.split("."); left, right, y = xy[kind]
        joints.append({"joint_id": joint, "position": [left if side == "left" else right, y],
                       "source": "pose", "displacement_px": 0})
    return candidate, {"schema": "autospine.joint-optimization/v1", "authority": "none", "diagnostic_only": True,
                       "status": "candidate_requires_review", "candidate_sha256": canonical_sha256(candidate), "joints": joints}


class CanonicalSkeletonTests(unittest.TestCase):
    def test_expected_topology_minimum_lengths_and_honest_sources(self):
        candidate, optimization = fixture(); original = deepcopy((candidate, optimization))
        result = build_canonical_skeleton(candidate, optimization)
        self.assertEqual(result["status"], "candidate_requires_review")
        self.assertEqual((candidate, optimization), original)
        bones = {row["id"]: row for row in result["bones"]}
        self.assertEqual(len(bones), 20)
        self.assertIsNone(bones["root"]["parent_id"])
        for child, parent in (("pelvis", "root"), ("chest", "spine"), ("clavicle_l", "chest"),
                              ("upperarm_l", "clavicle_l"), ("hand_r", "forearm_r"), ("thigh_r", "pelvis")):
            self.assertEqual(bones[child]["parent_id"], parent)
        self.assertTrue(all(row["length"] >= 1 for row in bones.values()))
        for name in ("root", "chest", "neck", "head", "hand_l", "foot_r"):
            self.assertEqual(bones[name]["provenance"]["kind"], "fallback")
        self.assertEqual(bones["forearm_l"]["provenance"]["kind"], "optimized")
        self.assertEqual(bones["forearm_l"]["head_xy"], [100, 260])

    def test_setup_fk_reconstructs_all_heads_tails(self):
        result = build_canonical_skeleton(*fixture()); frames = {}
        for row in result["bones"]:
            origin, angle = frames[row["parent_id"]] if row["parent_id"] else ([0, 0], 0)
            local = row["setup_local"]; radians = math.radians(angle)
            head = [origin[0] + local["x"]*math.cos(radians)-local["y"]*math.sin(radians),
                    origin[1] + local["x"]*math.sin(radians)+local["y"]*math.cos(radians)]
            rotation = angle + local["rotation_degrees"]
            tail = [head[0]+row["length"]*math.cos(math.radians(rotation)),
                    head[1]+row["length"]*math.sin(math.radians(rotation))]
            for actual, expected in zip(head+tail, row["head_xy"]+row["tail_xy"]):
                self.assertAlmostEqual(actual, expected, places=9)
            frames[row["id"]] = (head, rotation)

    def test_zero_length_and_out_of_canvas_fallback_block_without_clamping(self):
        for replacements in ({"elbow.left": [130, 180]}, {"ankle.right": [240, 600]},
                             {"shoulder.left": [130, 10], "shoulder.right": [270, 10]}):
            candidate, optimization = fixture()
            for row in optimization["joints"]:
                if row["joint_id"] in replacements: row["position"] = replacements[row["joint_id"]]
            result = build_canonical_skeleton(candidate, optimization)
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["bones"], [])
            self.assertTrue(result["reason_codes"])

    def test_optimizer_blocked_stays_blocked(self):
        candidate, optimization = fixture(); optimization.update(status="blocked", joints=[])
        result = build_canonical_skeleton(candidate, optimization)
        self.assertEqual(result["reason_codes"], ["joint_optimization_blocked"])
        self.assertEqual(result["bones"], [])

    def test_wrong_identity_ids_nonfinite_and_huge_numbers_rejected(self):
        for mutate in (lambda d: d.update(candidate_sha256="0"*64), lambda d: d["joints"].reverse(),
                       lambda d: d["joints"][0].update(position=[True, 0]),
                       lambda d: d["joints"][0].update(position=[float("nan"), 0]),
                       lambda d: d["joints"][0].update(position=[10**1000, 0])):
            candidate, optimization = fixture(); mutate(optimization)
            with self.assertRaises(ValueError): build_canonical_skeleton(candidate, optimization)

    def test_replay_rejects_parent_or_local_transform_tampering(self):
        candidate, optimization = fixture(); result = build_canonical_skeleton(candidate, optimization)
        self.assertEqual(validate_canonical_skeleton(candidate, optimization, result), result)
        for mutate in (lambda d: d["bones"][1].update(parent_id="head"),
                       lambda d: d["bones"][3]["setup_local"].update(x=123),
                       lambda d: d.update(authority="approved")):
            modified = deepcopy(result); mutate(modified)
            with self.assertRaises(ValueError): validate_canonical_skeleton(candidate, optimization, modified)


if __name__ == "__main__": unittest.main()
