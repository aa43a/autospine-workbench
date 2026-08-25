"""P5 motion target projection and exact verified-input binding tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json
import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test extra
    Draft202012Validator = None

from autospine_workbench.ik_bundle_contract import build_ik_bundle_contract  # noqa: E402
from autospine_workbench.ik_bundle_integrity import VerifiedIkBundle  # noqa: E402
from autospine_workbench.ik_probe_report import build_ik_probe_report  # noqa: E402
from autospine_workbench.ik_target_profile import compile_ik_target_profile  # noqa: E402
from autospine_workbench.mesh_bundle_integrity import VerifiedMeshBundle  # noqa: E402
from autospine_workbench.motion_roles import CANONICAL_BONE_ROLE_ITEMS  # noqa: E402
from autospine_workbench.motion_target_profile import (  # noqa: E402
    MotionTargetProfileError,
    compile_motion_target_profile,
)
from autospine_workbench.motion_target_geometry import (  # noqa: E402
    GEOMETRY_TOLERANCE_PX,
)
from autospine_workbench.motion_target_validation import (  # noqa: E402
    MotionTargetValidationError,
    require_motion_target_profile,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from tests.test_ik_target_profile import verified_bundle  # noqa: E402


def setup(x, y, rotation, length, *, scale_x=1, scale_y=1):
    return {
        "x": x, "y": y, "rotation_deg": rotation,
        "scale_x": scale_x, "scale_y": scale_y, "length": length,
    }


def full_rig(*, reverse=False):
    bones = [
        {"id": "root-pelvis", "parent": None, "setup": setup(200, 360, -90, 20)},
        {"id": "pelvis-spine", "parent": "root-pelvis", "setup": setup(20, 0, 0, 50)},
        {"id": "spine-chest", "parent": "pelvis-spine", "setup": setup(50, 0, 0, 60)},
        {"id": "chest-neck", "parent": "spine-chest", "setup": setup(60, 0, 0, 20)},
        {"id": "neck-head", "parent": "chest-neck", "setup": setup(20, 0, 0, 25)},
    ]
    for side, clavicle_rotation, arm_rotation, forearm_rotation in (
        ("left", 90, 60, -30), ("right", -90, -60, 30),
    ):
        bones.extend([
            {"id": f"chest-shoulder.{side}", "parent": "spine-chest",
             "setup": setup(60, 0, clavicle_rotation, 35)},
            {"id": f"upper-arm.{side}", "parent": f"chest-shoulder.{side}",
             "setup": setup(35, 0, arm_rotation, 35)},
            {"id": f"forearm.{side}", "parent": f"upper-arm.{side}",
             "setup": setup(35, 0, forearm_rotation, 30)},
        ])
    for side, hip_rotation, thigh_rotation, calf_rotation in (
        ("left", 90, 90, -20), ("right", -90, -90, 20),
    ):
        bones.extend([
            {"id": f"pelvis-hip.{side}", "parent": "root-pelvis",
             "setup": setup(20, 0, hip_rotation, 15)},
            {"id": f"thigh.{side}", "parent": f"pelvis-hip.{side}",
             "setup": setup(15, 0, thigh_rotation, 55)},
            {"id": f"calf.{side}", "parent": f"thigh.{side}",
             "setup": setup(55, 0, calf_rotation, 45)},
        ])
    if reverse:
        bones.reverse()
    return {
        "format": "autospine-rig-ir", "format_version": 1,
        "canvas": {
            "width": 400, "height": 400, "origin": "top_left",
            "x_axis": "right", "y_axis": "down", "units": "pixel",
        },
        "bones": bones, "attachments": [], "animations": [],
        "qa": {"status": "passed", "checks": []},
    }


def mesh_fixture(rig=None, *, converted=False):
    rig = deepcopy(rig or full_rig())
    base = verified_bundle(rig, converted=False)
    targets = []
    if converted:
        targets = [{
            "attachment_id": "leg-left", "source_layer_id": "leg-left",
            "side": "left", "proximal_bone_id": "thigh.left",
            "distal_bone_id": "calf.left",
        }]
    probes = {"status": "passed"}
    visuals = {
        "status": "passed",
        "summary": f"converted={len(targets)}" if targets else "reviewed-noop",
        "targets": targets,
    }
    documents = (
        ("rig.json", _encode(rig)), ("run-manifest.json", "{}"),
        ("probes.json", _encode(probes)), ("visuals.json", _encode(visuals)),
    )
    return VerifiedMeshBundle(
        path=base.path, project_id=base.project_id,
        rig_sha256=base.rig_sha256, run_sha256=base.run_sha256,
        probes_sha256=base.probes_sha256, visuals_sha256=base.visuals_sha256,
        bundle_sha256=base.bundle_sha256,
        base_rig_sha256=base.base_rig_sha256,
        base_bundle_sha256=base.base_bundle_sha256,
        layer_manifest_sha256=base.layer_manifest_sha256,
        resolved_project_sha256=base.resolved_project_sha256,
        _document_json_items=documents, _png_items=(),
    )


def ik_fixture(mesh):
    profile = compile_ik_target_profile(mesh).document
    probes = build_ik_probe_report(profile).document
    contract = build_ik_bundle_contract(mesh.project_id, profile, probes)
    return VerifiedIkBundle(
        path=Path("synthetic-p4"), project_id=mesh.project_id,
        profile_sha256=contract.profile_sha256,
        probes_sha256=contract.probes_sha256,
        bundle_sha256=contract.bundle_sha256,
        p3_rig_sha256=mesh.rig_sha256,
        p3_bundle_sha256=mesh.bundle_sha256,
        _source_json=_encode(profile["source"]),
        _document_json_items=(
            ("profile.json", _encode(profile)),
            ("probes.json", _encode(probes)),
        ),
    )


def pair(*, converted=False, rig=None):
    mesh = mesh_fixture(rig, converted=converted)
    return ik_fixture(mesh), mesh


def _encode(value):
    return json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":"))


class MotionTargetProfileTests(unittest.TestCase):
    def test_projects_17_roles_full_handles_body_frame_and_reference(self):
        ik, mesh = pair(converted=True)
        before = (deepcopy(ik.profile), deepcopy(mesh.rig))
        first = compile_motion_target_profile(ik, mesh)
        second = compile_motion_target_profile(ik, mesh)
        document = first.document

        self.assertEqual(first, second)
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(17, len(document["bones"]))
        self.assertEqual(list(CANONICAL_BONE_ROLE_ITEMS), [
            (item["role"], item["bone_id"]) for item in document["bones"]
        ])
        self.assertEqual(ik.profile["handles"], document["ik_handles"])
        self.assertEqual(ik.profile_sha256, document["source"]["p4_profile_sha256"])
        self.assertEqual(ik.source_identities, document["source"]["p3"])
        frame = document["body_frame"]
        self.assertEqual([0.0, -1.0], frame["up_xy"])
        self.assertEqual([1.0, 0.0], frame["left_outward_xy"])
        self.assertEqual([-1.0, 0.0], frame["right_outward_xy"])
        self.assertFalse(frame["screen_x_inference"])
        self.assertEqual(100.0, document["reference_length"]["value_px"])
        self.assertEqual("converted", document["mesh_evidence"]["status"])
        self.assertEqual(["leg-left"], [
            item["attachment_id"]
            for item in document["mesh_evidence"]["target_inventory"]
        ])
        self.assertEqual(before, (ik.profile, mesh.rig))
        require_motion_target_profile(document, verified_ik=ik, verified_mesh=mesh)

        changed = first.document
        changed["bones"].clear()
        self.assertEqual(17, len(first.bones))
        with self.assertRaises(FrozenInstanceError):
            first._document_json = "{}"  # type: ignore[misc]

    def test_reviewed_noop_is_explicit_and_bone_input_order_is_irrelevant(self):
        ik, mesh = pair()
        normal = compile_motion_target_profile(ik, mesh).document
        self.assertEqual("reviewed-noop", normal["mesh_evidence"]["status"])
        self.assertEqual([], normal["mesh_evidence"]["target_inventory"])

        reversed_ik, reversed_mesh = pair(rig=full_rig(reverse=True))
        reversed_document = compile_motion_target_profile(
            reversed_ik, reversed_mesh
        ).document
        self.assertEqual(normal["bones"], reversed_document["bones"])
        self.assertEqual(normal["body_frame"], reversed_document["body_frame"])
        self.assertEqual(normal["reference_length"], reversed_document["reference_length"])

    def test_binding_and_document_tamper_fail_closed(self):
        ik, mesh = pair()
        baseline = compile_motion_target_profile(ik, mesh).document
        with self.assertRaisesRegex(MotionTargetProfileError, "content address"):
            compile_motion_target_profile(
                replace(ik, bundle_sha256="f" * 64), mesh
            )
        with self.assertRaises(MotionTargetProfileError):
            compile_motion_target_profile(
                ik, replace(mesh, bundle_sha256="f" * 64)
            )

        mutations = (
            lambda value: value["source"].update(p4_bundle_sha256="f" * 64),
            lambda value: value["bones"].reverse(),
            lambda value: value["ik_handles"][0]["root_xy"].__setitem__(0, math.nan),
            lambda value: value["body_frame"]["up_xy"].__setitem__(0, 0.1),
            lambda value: value["mesh_evidence"].update(status="converted"),
        )
        for mutate in mutations:
            changed = deepcopy(baseline)
            mutate(changed)
            with self.assertRaises(MotionTargetValidationError):
                require_motion_target_profile(
                    changed, verified_ik=ik, verified_mesh=mesh
                )

    def test_non_json_arrays_unsafe_project_scale_and_disconnection_fail(self):
        ik, mesh = pair()
        document = compile_motion_target_profile(ik, mesh).document
        document["body_frame"]["up_xy"] = (0.0, -1.0)
        with self.assertRaisesRegex(MotionTargetValidationError, "JSON lists"):
            require_motion_target_profile(document)
        unsafe = compile_motion_target_profile(ik, mesh).document
        unsafe["project_id"] = "../escape"
        with self.assertRaises(MotionTargetValidationError):
            require_motion_target_profile(unsafe)

        scaled = full_rig()
        self.bone(scaled, "neck-head")["setup"]["scale_x"] = 2
        scaled_mesh = mesh_fixture(scaled)
        with self.assertRaisesRegex(MotionTargetProfileError, "unit scale"):
            compile_motion_target_profile(ik_fixture(scaled_mesh), scaled_mesh)

        disconnected = full_rig()
        self.bone(disconnected, "neck-head")["setup"]["x"] += 1
        disconnected_mesh = mesh_fixture(disconnected)
        with self.assertRaisesRegex(MotionTargetProfileError, "disconnected"):
            compile_motion_target_profile(
                ik_fixture(disconnected_mesh), disconnected_mesh
            )

    def test_standalone_validator_cross_binds_bones_handles_and_body_frame(self):
        ik, mesh = pair()
        baseline = compile_motion_target_profile(ik, mesh).document
        mutations = (
            ("thigh.left", "length_px", 1.0),
            ("upper-arm.left", "rotation_deg", 5.0),
            ("pelvis-spine", "x", 1.0),
        )
        for bone_id, field, delta in mutations:
            changed = deepcopy(baseline)
            bone = next(item for item in changed["bones"] if item["bone_id"] == bone_id)
            bone["setup_local"][field] += delta
            with self.subTest(bone_id=bone_id, field=field), self.assertRaises(
                MotionTargetValidationError
            ):
                require_motion_target_profile(changed)

    def test_standalone_geometry_comparison_tolerates_only_fk_roundoff(self):
        ik, mesh = pair()
        baseline = compile_motion_target_profile(ik, mesh).document
        roundoff = deepcopy(baseline)
        roundoff["ik_handles"][0]["root_xy"][0] += 1e-12
        roundoff["body_frame"]["pelvis_xy"][0] += 1e-12
        require_motion_target_profile(roundoff)

        outside = deepcopy(baseline)
        outside["body_frame"]["pelvis_xy"][0] += 2 * GEOMETRY_TOLERANCE_PX
        with self.assertRaises(MotionTargetValidationError):
            require_motion_target_profile(outside)

        boolean = deepcopy(baseline)
        boolean["body_frame"]["pelvis_xy"][0] = False
        with self.assertRaises(MotionTargetValidationError):
            require_motion_target_profile(boolean)

    def test_degenerate_body_axes_fail_without_screen_x_side_repair(self):
        same_side = full_rig()
        self.bone(same_side, "chest-shoulder.right")["setup"]["rotation_deg"] = 90
        mesh = mesh_fixture(same_side)
        with self.assertRaisesRegex(MotionTargetProfileError, "not opposed"):
            compile_motion_target_profile(ik_fixture(mesh), mesh)

        zero_up = full_rig()
        self.bone(zero_up, "spine-chest")["setup"].update(
            rotation_deg=180, length=50
        )
        for bone_id in (
            "chest-neck", "chest-shoulder.left", "chest-shoulder.right",
        ):
            self.bone(zero_up, bone_id)["setup"]["x"] = 50
        mesh = mesh_fixture(zero_up)
        with self.assertRaisesRegex(MotionTargetProfileError, "degenerate"):
            compile_motion_target_profile(ik_fixture(mesh), mesh)

    @unittest.skipIf(Draft202012Validator is None, "install the test extra")
    def test_schema_is_valid_and_accepts_exact_profile(self):
        schema = json.loads(
            (ROOT / "schemas" / "motion-target-profile-v1.schema.json").read_text("utf-8")
        )
        Draft202012Validator.check_schema(schema)
        document = compile_motion_target_profile(*pair()).document
        self.assertEqual([], list(Draft202012Validator(schema).iter_errors(document)))

    @staticmethod
    def bone(rig, bone_id):
        return next(item for item in rig["bones"] if item["id"] == bone_id)


if __name__ == "__main__":
    unittest.main()
