from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.body_sway_probe_math import BodySwayPoseSample
from autospine_workbench.region_rebind_candidates import (
    RegionRebindCandidateError,
    compile_region_rebind_candidates,
)
from autospine_workbench.region_rebind_validation import (
    RegionRebindValidationError,
    region_rebind_candidates_sha256,
    require_region_rebind_candidate_binding,
    require_region_rebind_candidates,
)


MOTION_SHA = "a" * 64
BODY_IDS = ("pelvis-spine", "spine-chest", "chest-neck", "neck-head")


def _setup(x, y, rotation, length):
    return {
        "x": x, "y": y, "rotation_deg": rotation,
        "scale_x": 1.0, "scale_y": 1.0, "length": length,
    }


def rig_fixture():
    bones = [
        {"id": "root-pelvis", "parent": None, "setup": _setup(0, 0, 0, 1)},
        {"id": "pelvis-spine", "parent": "root-pelvis", "setup": _setup(1, 0, 0, 1)},
        {"id": "spine-chest", "parent": "pelvis-spine", "setup": _setup(1, 0, 0, 1)},
        {"id": "chest-neck", "parent": "spine-chest", "setup": _setup(1, 0, 0, 1)},
        {"id": "neck-head", "parent": "chest-neck", "setup": _setup(1, 0, 0, 1)},
        {"id": "upper-arm.left", "parent": "root-pelvis", "setup": _setup(10, 10, 0, 40)},
        {"id": "forearm.left", "parent": "upper-arm.left", "setup": _setup(40, 0, 0, 40)},
    ]
    return {
        "format": "autospine-rig-ir", "format_version": 1,
        "canvas": {
            "width": 100, "height": 100, "origin": "top_left",
            "x_axis": "right", "y_axis": "down", "units": "pixel",
        },
        "bones": bones,
        "slots": [{
            "id": "sleeve", "bone": "forearm.left",
            "setup_attachment": "sleeve", "setup_draw_order": 0,
        }],
        "attachments": [{
            "id": "sleeve", "type": "region", "slot": "sleeve",
            "canvas_offset_xy": [5, 5], "size": [90, 30],
            "pivot_xy": [90, 10],
        }],
        "skins": {"default": {"sleeve": ["sleeve"]}},
        "animations": [], "capabilities": ["region_attachment"],
    }


def sample(tick, upper, forearm):
    base = {bone_id: 0.0 for bone_id in BODY_IDS}
    base.update({"upper-arm.left": float(upper), "forearm.left": float(forearm)})
    base_rows = tuple(sorted(base.items()))
    overlay = tuple((bone_id, 0.0) for bone_id in BODY_IDS)
    return BodySwayPoseSample(
        tick=tick,
        base_rotation_deg=base_rows,
        overlay_rotation_deg=overlay,
        combined_rotation_deg=base_rows,
        root_translation_xy=(0.0, 0.0),
    )


def motion_samples():
    return (sample(0, 0, 0), sample(1, 5, 90), sample(2, -5, -90))


class RegionRebindCandidateTests(unittest.TestCase):
    def compile(self, **kwargs):
        return compile_region_rebind_candidates(
            kwargs.pop("rig", rig_fixture()),
            kwargs.pop("samples", motion_samples()),
            project_id="sample", motion_sha256=kwargs.pop("motion_sha", MOTION_SHA),
            attachment_id="sleeve", **kwargs,
        )

    def test_parent_is_recommended_for_region_spanning_both_segments(self):
        artifact = self.compile()
        document = artifact.document
        require_region_rebind_candidates(document)
        self.assertEqual("recommended", document["recommendation"]["status"])
        self.assertEqual("upper-arm.left", document["recommendation"]["to_bone_id"])
        self.assertEqual("none", document["recommendation"]["authority"])
        self.assertTrue(document["recommendation"]["requires_explicit_review"])
        rows = {row["bone_id"]: row for row in document["candidates"]}
        self.assertEqual(
            ["forearm.left", "upper-arm.left"],
            rows["upper-arm.left"]["metrics"][
                "setup_subtree_segment_ids_fully_inside_region"
            ],
        )
        self.assertLess(
            rows["upper-arm.left"]["metrics"]["normalized_centroid_motion_rms"],
            rows["forearm.left"]["metrics"]["normalized_centroid_motion_rms"],
        )
        self.assertLessEqual(
            rows["upper-arm.left"]["metrics"]["setup_reconstruction_max_error_px"],
            1e-7,
        )

    def test_artifact_is_deterministic_and_exactly_bound(self):
        left, right = self.compile(), self.compile()
        self.assertEqual(left.canonical_bytes, right.canonical_bytes)
        self.assertEqual(left.sha256, region_rebind_candidates_sha256(left.document))
        detached = left.document
        detached["status"] = "tampered"
        self.assertEqual("candidate_only", left.document["status"])
        require_region_rebind_candidate_binding(
            left.document, rig_fixture(), motion_samples(),
            project_id="sample", motion_sha256=MOTION_SHA,
            attachment_id="sleeve",
        )

    def test_motion_and_rig_identity_changes_do_not_reuse_candidate(self):
        baseline = self.compile()
        changed_motion = self.compile(motion_sha="b" * 64)
        changed_rig = rig_fixture()
        changed_rig["attachments"][0]["pivot_xy"] = [89, 10]
        changed = self.compile(rig=changed_rig)
        self.assertNotEqual(baseline.sha256, changed_motion.sha256)
        self.assertNotEqual(baseline.sha256, changed.sha256)
        self.assertNotEqual(
            baseline.document["source"]["rig_sha256"],
            changed.document["source"]["rig_sha256"],
        )

    def test_motion_extent_alone_cannot_trigger_recommendation(self):
        still = (sample(0, 0, 0), sample(1, 0, 0))
        result = self.compile(samples=still).document
        self.assertEqual("ambiguous", result["recommendation"]["status"])
        self.assertIn(
            "insufficient_combined_spatial_and_motion_evidence",
            result["recommendation"]["reason_codes"],
        )

    def test_explicit_scope_rejects_non_neighbor_and_missing_current(self):
        for values in (
            ["forearm.left", "root-pelvis"], ["upper-arm.left"],
        ):
            with self.subTest(values=values), self.assertRaises(RegionRebindCandidateError):
                self.compile(candidate_bone_ids=values)

    def test_tampering_and_wrong_exact_input_fail_closed(self):
        artifact = self.compile()
        tampered = deepcopy(artifact.document)
        tampered["candidates"][0]["metrics"][
            "normalized_centroid_motion_rms"
        ] += 0.01
        with self.assertRaises(RegionRebindValidationError):
            require_region_rebind_candidates(tampered)
        with self.assertRaises(RegionRebindValidationError):
            require_region_rebind_candidate_binding(
                artifact.document, rig_fixture(), motion_samples(),
                project_id="sample", motion_sha256="b" * 64,
                attachment_id="sleeve",
            )

    def test_schema_accepts_compiler_output_when_jsonschema_is_available(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is optional")
        schema = json.loads(
            (Path(__file__).parents[1] / "schemas" /
             "region-rebind-candidates-v1.schema.json").read_text("utf-8")
        )
        jsonschema.Draft202012Validator(schema).validate(self.compile().document)


if __name__ == "__main__":
    unittest.main()
