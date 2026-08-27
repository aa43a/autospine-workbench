"""Public interval pose extraction and P10.4b2 byte-lock tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.body_sway_continuous_interval_geometry import (  # noqa: E402
    assess_body_sway_interval_box,
)
from autospine_workbench.body_sway_continuous_proof import (  # noqa: E402
    compile_body_sway_continuous_preview_proof,
)
from autospine_workbench.body_sway_interval_arithmetic import (  # noqa: E402
    OutwardInterval,
)
from autospine_workbench.body_sway_interval_pose import (  # noqa: E402
    BodySwayIntervalPoseError,
    apply_body_sway_interval_matrix,
    body_sway_interval_rotation_deltas,
    prepare_body_sway_interval_pose,
    skin_body_sway_interval_binding,
)
from autospine_workbench.body_sway_probe_geometry_context import (  # noqa: E402
    prepare_body_sway_geometry_context,
)
from tests.body_sway_continuous_proof_helpers import (  # noqa: E402
    admitted_continuous_proof_inputs,
)
from tests.body_sway_probe_geometry_helpers import (  # noqa: E402
    exact_rig_and_target,
    sample,
)
from tests.p10_review_admission_helpers import (  # noqa: E402
    P10ReviewAdmissionFixture,
)


LEGACY_POSE_ORACLE_BYTES = 6_396
LEGACY_POSE_ORACLE_SHA256 = (
    "9046a61de62ed245a423f7d0af8f59e7691cc1cee66a4e1e9dbde75402d5de03"
)
# The lock includes the strict P0 resolved snapshot fixture.  Refresh it only
# when that fixture is intentionally resealed with canvas-valid joint geometry.
P104B2_CANONICAL_BYTES = 269_927
P104B2_CANONICAL_SHA256 = (
    "f4f43238c3b547172493507c3558376c5a579cfe4db806bb5c1e31e6dc061c7a"
)


class BodySwayIntervalPoseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        rig, target = exact_rig_and_target()
        cls.context = prepare_body_sway_geometry_context(rig, target)
        cls.left = sample(
            base={
                "pelvis-spine": -1.25, "spine-chest": 2.5,
                "calf.left": -3.75,
            },
            overlay={
                "pelvis-spine": -8.0, "spine-chest": 3.5,
                "chest-neck": 1.25, "neck-head": -2.0,
            }, translation=(-2.25, 3.5), tick=10,
        )
        cls.right = sample(
            base={
                "pelvis-spine": 4.75, "spine-chest": -1.5,
                "calf.left": 12.0,
            },
            overlay={
                "pelvis-spine": 9.0, "spine-chest": -5.25,
                "chest-neck": -3.0, "neck-head": 4.5,
            }, translation=(7.125, -1.75), tick=20,
        )
        cls.time = OutwardInterval(0.125, 0.75)
        cls.gain = OutwardInterval(0.2, 0.9)

    def test_public_pose_skin_and_assessment_match_legacy_oracle(self):
        pose = self._pose()
        vertices = tuple(
            skin_body_sway_interval_binding(pose, row.binding)
            for row in self.context.attachments
        )
        assessment = assess_body_sway_interval_box(**self._arguments())
        payload = _oracle_payload(pose, vertices, assessment)
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")

        self.assertEqual(LEGACY_POSE_ORACLE_BYTES, len(encoded))
        self.assertEqual(
            LEGACY_POSE_ORACLE_SHA256, hashlib.sha256(encoded).hexdigest()
        )
        self.assertEqual(
            (-1.0781250006250014, 4.781250001250005),
            tuple(_ends(pose.root_translation_xy[0])),
        )
        self.assertEqual(
            (-0.4375000012500024, 2.8437500006250014),
            tuple(_ends(pose.root_translation_xy[1])),
        )

    def test_pose_is_frozen_and_apply_is_a_public_exact_primitive(self):
        pose = self._pose()
        point = self.context.attachments[0].binding._vertices[0]
        applied = apply_body_sway_interval_matrix(
            pose.skin_matrices[0], point
        )
        self.assertTrue(all(value.finite for value in applied))
        with self.assertRaises(FrozenInstanceError):
            pose.root_translation_xy = applied  # type: ignore[misc]

    def test_non_finite_non_q9_and_wrong_inputs_fail_closed(self):
        mutations = (
            {"context": object()},
            {"time_fraction": OutwardInterval(-math.inf, 0.5)},
            {"time_fraction": OutwardInterval(-0.1, 0.5)},
            {"gain": OutwardInterval(0.0, math.inf)},
            {"left_root_translation_xy": (float("nan"), 0.0)},
            {"left_root_translation_xy": (-0.0, 0.0)},
            {"left_root_translation_xy": (0.1234567891, 0.0)},
            {"left_base_rotation_deg": {"unknown": 0.0}},
            {"left_base_rotation_deg": {"pelvis-spine": float("inf")}},
        )
        for mutation in mutations:
            arguments = self._arguments()
            arguments.update(mutation)
            with self.subTest(mutation=tuple(mutation)), self.assertRaises(
                BodySwayIntervalPoseError
            ):
                prepare_body_sway_interval_pose(**arguments)

    def test_public_rotation_apply_and_skin_reject_crosswired_inputs(self):
        with self.assertRaises(BodySwayIntervalPoseError):
            body_sway_interval_rotation_deltas(
                self.context.skinning_rig,
                {"pelvis-spine": float("nan")}, {}, {}, {},
                time_fraction=self.time, gain=self.gain,
            )
        pose = self._pose()
        bad_matrix = tuple(
            OutwardInterval(-math.inf, math.inf) for _index in range(6)
        )
        with self.assertRaises(BodySwayIntervalPoseError):
            apply_body_sway_interval_matrix(bad_matrix, (0.0, 0.0))
        with self.assertRaises(BodySwayIntervalPoseError):
            apply_body_sway_interval_matrix(pose.skin_matrices[0], (0.0, math.inf))

        other_rig, other_target = exact_rig_and_target()
        other = prepare_body_sway_geometry_context(other_rig, other_target)
        with self.assertRaises(BodySwayIntervalPoseError):
            skin_body_sway_interval_binding(
                pose, other.attachments[0].binding
            )

    def _arguments(self):
        return {
            "context": self.context,
            "left_base_rotation_deg": dict(self.left.base_rotation_deg),
            "right_base_rotation_deg": dict(self.right.base_rotation_deg),
            "left_overlay_rotation_deg": dict(self.left.overlay_rotation_deg),
            "right_overlay_rotation_deg": dict(self.right.overlay_rotation_deg),
            "left_root_translation_xy": self.left.root_translation_xy,
            "right_root_translation_xy": self.right.root_translation_xy,
            "time_fraction": self.time, "gain": self.gain,
        }

    def _pose(self):
        return prepare_body_sway_interval_pose(**self._arguments())


class BodySwayP104B2CanonicalLockTests(unittest.TestCase):
    def test_full_proof_canonical_bytes_and_sha_are_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = P10ReviewAdmissionFixture(Path(directory))
            inputs = admitted_continuous_proof_inputs(fixture)
            proof = compile_body_sway_continuous_preview_proof(inputs)

        bones = proof.document["source"]["rig_ir"]["bones"]
        root = next(bone for bone in bones if bone["id"] == "root-pelvis")
        self.assertEqual(320.0, root["setup"]["y"])
        self.assertEqual({0.75}, {
            bone["inference"]["confidence"] for bone in bones
        })
        self.assertEqual(P104B2_CANONICAL_BYTES, len(proof.canonical_bytes))
        self.assertEqual(P104B2_CANONICAL_SHA256, proof.sha256)
        self.assertEqual(
            P104B2_CANONICAL_SHA256,
            hashlib.sha256(proof.canonical_bytes).hexdigest(),
        )


def _oracle_payload(pose, vertices, assessment):
    bounds = assessment.bounds
    return {
        "deltas": [
            [bone_id, _ends(value)]
            for bone_id, value in pose.rotation_deltas_deg
        ],
        "matrices": [
            [_ends(value) for value in matrix]
            for matrix in pose.skin_matrices
        ],
        "root": [_ends(value) for value in pose.root_translation_xy],
        "vertices": [
            [[_ends(x), _ends(y)] for x, y in attachment]
            for attachment in vertices
        ],
        "assessment": {
            "status": assessment.status,
            "reason_codes": list(assessment.reason_codes),
            "bounds": [
                bounds.canvas_margin_lower_px,
                bounds.min_signed_area_ratio_lower,
                bounds.max_signed_area_ratio_upper,
                bounds.max_edge_stretch_squared_ratio_upper,
            ],
            "counts": [
                assessment.attachment_count, assessment.vertex_count,
                assessment.triangle_count, assessment.edge_count,
            ],
        },
    }


def _ends(value: OutwardInterval) -> list[float]:
    return [value.lower, value.upper]


if __name__ == "__main__":
    unittest.main()
