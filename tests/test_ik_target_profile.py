"""P4 target-profile contracts bound to synthetic verified P3 bundles."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
import math
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.ik_target_profile import (  # noqa: E402
    IkTargetProfileError,
    compile_ik_target_profile,
)
from autospine_workbench.ik_target_profile_validation import (  # noqa: E402
    IkTargetProfileValidationError,
    require_ik_target_profile,
)
from autospine_workbench.mesh_bundle_integrity import VerifiedMeshBundle  # noqa: E402
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional local validator
    Draft202012Validator = None


def setup(x, y, rotation, length, *, scale_x=1, scale_y=1):
    return {
        "x": x, "y": y, "rotation_deg": rotation,
        "scale_x": scale_x, "scale_y": scale_y, "length": length,
    }


def canonical_rig(*, reverse=False, converted=True):
    bones = [
        {"id": "root", "parent": None, "setup": setup(20, 20, 5, 10)},
        {"id": "upper-arm.left", "parent": "root", "setup": setup(80, 60, 15, 30)},
        {"id": "forearm.left", "parent": "upper-arm.left", "setup": setup(30, 0, 50, 25)},
        {"id": "upper-arm.right", "parent": "root", "setup": setup(260, 60, 145, 30)},
        {"id": "forearm.right", "parent": "upper-arm.right", "setup": setup(30, 0, -50, 25)},
        {"id": "thigh.left", "parent": "root", "setup": setup(140, 170, 70, 50)},
        {"id": "calf.left", "parent": "thigh.left", "setup": setup(50, 0, -25, 45)},
        {"id": "thigh.right", "parent": "root", "setup": setup(240, 170, 100, 50)},
        {"id": "calf.right", "parent": "thigh.right", "setup": setup(50, 0, 25, 45)},
    ]
    if reverse:
        bones.reverse()
    return {
        "format": "autospine-rig-ir", "format_version": 1,
        "canvas": {
            "width": 400, "height": 400, "origin": "top_left",
            "x_axis": "right", "y_axis": "down", "units": "pixel",
        },
        "bones": bones,
        "attachments": ([{"id": "mesh-leg", "type": "mesh"}] if converted else []),
        "animations": [],
    }


def verified_bundle(rig=None, *, converted=True, identity_offset=0):
    rig = deepcopy(rig if rig is not None else canonical_rig(converted=converted))
    values = [f"{value:x}" * 64 for value in range(1 + identity_offset, 9 + identity_offset)]
    encoded = json.dumps(rig, sort_keys=True, separators=(",", ":"))
    documents = (
        ("rig.json", encoded), ("run-manifest.json", "{}"),
        ("probes.json", "{}"), ("visuals.json", "{}"),
    )
    return VerifiedMeshBundle(
        path=Path("synthetic-p3"), project_id="synthetic-p3",
        rig_sha256=canonical_sha256(rig), run_sha256=values[0],
        probes_sha256=values[1], visuals_sha256=values[2],
        bundle_sha256=values[3], base_rig_sha256=values[4],
        base_bundle_sha256=values[5], layer_manifest_sha256=values[6],
        resolved_project_sha256=values[7],
        _document_json_items=documents, _png_items=(),
    )


class IkTargetProfileTests(unittest.TestCase):
    def test_converted_bundle_builds_four_bound_frozen_handles(self):
        bundle = verified_bundle(converted=True)
        first = compile_ik_target_profile(bundle)
        second = compile_ik_target_profile(bundle)
        self.assertEqual(first, second)
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(
            ["arm.left", "arm.right", "leg.left", "leg.right"],
            [item["id"] for item in first.handles],
        )
        self.assertEqual({
            "base_rig_sha256", "base_bundle_sha256", "layer_manifest_sha256",
            "resolved_project_sha256", "rig_sha256", "run_sha256",
            "probes_sha256", "visuals_sha256", "bundle_sha256",
        }, set(first.source))
        self.assertEqual(bundle.rig_sha256, first.source["rig_sha256"])
        self.assertEqual("positive-unit-only", first.document["solver"]["config"]["rigid_chain_scale"])
        self.assertIn("not-mesh-visual-safe-range", first.document["solver"]["config"]["kinematic_reach_semantics"])
        require_ik_target_profile(first.document, verified_bundle=bundle)

        changed = first.document
        changed["handles"][0]["root_xy"][0] += 1
        self.assertNotEqual(changed, first.document)
        with self.assertRaises(FrozenInstanceError):
            first._document_json = "{}"  # type: ignore[misc]

        if Draft202012Validator is not None:
            schema = json.loads((ROOT / "schemas" / "ik-target-profile-v1.schema.json").read_text("utf-8"))
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(schema).validate(first.document)

    def test_reviewed_noop_bundle_still_has_four_rigid_chain_handles(self):
        bundle = verified_bundle(converted=False, identity_offset=1)
        self.assertEqual([], bundle.rig["attachments"])
        profile = compile_ik_target_profile(bundle)
        self.assertEqual(4, len(profile.handles))
        self.assertTrue(all("kinematic_reach" in item for item in profile.handles))
        self.assertTrue(all(item["fallback_direction"]["source"] == "setup.root_to_effector"
                            for item in profile.handles))

    def test_bone_inventory_order_does_not_change_handles(self):
        normal = compile_ik_target_profile(verified_bundle(canonical_rig()))
        reversed_profile = compile_ik_target_profile(
            verified_bundle(canonical_rig(reverse=True))
        )
        self.assertEqual(normal.handles, reversed_profile.handles)
        self.assertNotEqual(normal.source["rig_sha256"], reversed_profile.source["rig_sha256"])

    def test_wrong_chain_collinear_and_scale_ancestry_fail_closed(self):
        cases = []
        wrong_chain = canonical_rig()
        self.bone(wrong_chain, "forearm.left")["parent"] = "root"
        cases.append((wrong_chain, "not direct"))
        collinear = canonical_rig()
        self.bone(collinear, "forearm.left")["setup"]["rotation_deg"] = 0
        cases.append((collinear, "collinear"))
        nonunit = canonical_rig()
        self.bone(nonunit, "root")["setup"]["scale_x"] = 2
        cases.append((nonunit, r"requires \+1"))
        negative = canonical_rig()
        self.bone(negative, "upper-arm.left")["setup"]["scale_y"] = -1
        cases.append((negative, r"requires \+1"))
        for rig, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(IkTargetProfileError, message):
                compile_ik_target_profile(verified_bundle(rig))

    def test_strict_validator_rejects_identity_nonfinite_order_and_roundtrip_drift(self):
        bundle = verified_bundle()
        baseline = compile_ik_target_profile(bundle).document
        cases = []
        identity = deepcopy(baseline)
        identity["source"]["bundle_sha256"] = "f" * 64
        cases.append(identity)
        nonfinite = deepcopy(baseline)
        nonfinite["handles"][0]["root_xy"][0] = math.nan
        cases.append(nonfinite)
        order = deepcopy(baseline)
        order["handles"][0], order["handles"][1] = order["handles"][1], order["handles"][0]
        cases.append(order)
        hinge = deepcopy(baseline)
        hinge["handles"][0]["hinge_xy"][0] += 0.01
        cases.append(hinge)
        angle = deepcopy(baseline)
        angle["handles"][0]["setup_angles_deg"]["proximal_local"] += 1
        cases.append(angle)
        extra = deepcopy(baseline)
        extra["handles"][0]["visual_safe_angle"] = [-10, 20]
        cases.append(extra)
        for index, document in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(IkTargetProfileValidationError):
                require_ik_target_profile(document, verified_bundle=bundle)

    def test_inner_validator_does_not_need_bundle_to_enforce_geometry(self):
        document = compile_ik_target_profile(verified_bundle()).document
        require_ik_target_profile(document)
        document["handles"][2]["kinematic_reach"]["maximum_px"] += 1
        with self.assertRaisesRegex(IkTargetProfileValidationError, "kinematic reach"):
            require_ik_target_profile(document)

    def test_unverified_input_type_is_rejected(self):
        with self.assertRaisesRegex(IkTargetProfileError, "VerifiedMeshBundleReader"):
            compile_ik_target_profile(SimpleNamespace(rig=canonical_rig()))  # type: ignore[arg-type]

    @staticmethod
    def bone(rig, bone_id):
        return next(item for item in rig["bones"] if item["id"] == bone_id)


if __name__ == "__main__":
    unittest.main()
