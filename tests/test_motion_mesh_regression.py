"""Clip-specific P3 mesh deformation regression tests."""

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

from autospine_workbench.motion_instance_validation import (  # noqa: E402
    require_motion_instance,
)
from autospine_workbench.motion_mesh_regression import (  # noqa: E402
    MotionMeshRegressionError,
    build_motion_mesh_regression,
    require_motion_mesh_regression,
)
from autospine_workbench.motion_target_profile import (  # noqa: E402
    compile_motion_target_profile,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.rig_fk import evaluate_world_setup  # noqa: E402
from tests.test_motion_instance_contract import instance_fixture  # noqa: E402
from tests.test_motion_target_profile import (  # noqa: E402
    full_rig,
    ik_fixture,
    mesh_fixture,
)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def attachment(rig, *, failing=False):
    world = evaluate_world_setup(rig["bones"])
    hinge = world["calf.left"]["origin_xy"]
    angle = math.radians(world["calf.left"]["rotation_deg"])
    direction = math.cos(angle), math.sin(angle)
    normal = -direction[1], direction[0]
    if failing:
        vertices = [
            hinge,
            [hinge[0] + 1000, hinge[1]],
            [hinge[0] + 1000, hinge[1] + 0.001],
        ]
        weights = [
            [{"bone": "thigh.left", "weight": 1.0}],
            [{"bone": "thigh.left", "weight": 1.0}],
            [{"bone": "calf.left", "weight": 1.0}],
        ]
    else:
        vertices = [
            hinge,
            [hinge[0] + 10 * direction[0], hinge[1] + 10 * direction[1]],
            [hinge[0] + 10 * normal[0], hinge[1] + 10 * normal[1]],
        ]
        weights = [
            [
                {"bone": "thigh.left", "weight": 0.5},
                {"bone": "calf.left", "weight": 0.5},
            ],
            [{"bone": "calf.left", "weight": 1.0}],
            [{"bone": "calf.left", "weight": 1.0}],
        ]
    return {
        "id": "leg-left",
        "slot": "leg-left",
        "type": "mesh",
        "source_layer_ids": ["leg-left"],
        "canvas_offset_xy": [0.0, 0.0],
        "vertices": [list(point) for point in vertices],
        "triangles": [0, 1, 2],
        "weights": weights,
    }


def exact_mesh_and_target(*, converted, failing=False):
    rig = full_rig()
    rig["attachments"] = [attachment(rig, failing=failing)] if converted else []
    provisional = mesh_fixture(rig, converted=converted)
    documents = dict(provisional._document_json_items)
    mesh = replace(
        provisional,
        rig_sha256=canonical_sha256(rig),
        run_sha256=canonical_sha256(json.loads(documents["run-manifest.json"])),
        probes_sha256=canonical_sha256(json.loads(documents["probes.json"])),
        visuals_sha256=canonical_sha256(json.loads(documents["visuals.json"])),
    )
    target = compile_motion_target_profile(ik_fixture(mesh), mesh)
    return mesh, target


def calf_bend_instance(target, angle=90.0):
    instance = instance_fixture(target.document)
    instance["tracks"].insert(0, {
        "bone_id": "calf.left",
        "property": "rotation",
        "keys": [
            {"tick": 0, "value": 0.0},
            {"tick": 500_000, "value": angle},
            {"tick": 1_000_000, "value": 0.0},
        ],
    })
    require_motion_instance(instance, target_profile=target.document)
    return instance


class MotionMeshRegressionTests(unittest.TestCase):
    def test_reviewed_noop_is_explicit_deterministic_and_frozen(self):
        mesh, target = exact_mesh_and_target(converted=False)
        instance = instance_fixture(target.document)
        before = deepcopy((instance, target.document, mesh.rig))
        first = build_motion_mesh_regression(instance, target.document, mesh)
        second = build_motion_mesh_regression(instance, target.document, mesh)
        self.assertEqual(first, second)
        self.assertEqual("passed", first.document["status"])
        self.assertEqual("reviewed-noop", first.document["summary"])
        self.assertEqual([], first.document["attachments"])
        require_motion_mesh_regression(
            first.document, instance=instance,
            target_profile=target.document, verified_mesh=mesh,
        )
        self.assertEqual(before, (instance, target.document, mesh.rig))
        changed = first.document
        changed["attachments"].append({})
        self.assertEqual([], first.document["attachments"])
        with self.assertRaises(FrozenInstanceError):
            first._document_json = "{}"  # type: ignore[misc]

    def test_shared_index_hinge_mesh_passes_full_sample_schedule(self):
        mesh, target = exact_mesh_and_target(converted=True)
        instance = calf_bend_instance(target, angle=45.0)
        report = build_motion_mesh_regression(instance, target.document, mesh)
        entry = report.document["attachments"][0]
        self.assertEqual("passed", report.document["status"])
        self.assertEqual("passed", entry["status"])
        self.assertEqual(0, entry["failed_tick_count"])
        self.assertEqual(0, entry["worst"]["max_flipped_count"])
        self.assertEqual(0.0, entry["worst"]["max_interior_crack_gap_px"])

    def test_clip_specific_extreme_pose_is_rejected_with_failure_tick(self):
        mesh, target = exact_mesh_and_target(converted=True, failing=True)
        instance = calf_bend_instance(target, angle=90.0)
        report = build_motion_mesh_regression(instance, target.document, mesh)
        entry = report.document["attachments"][0]
        self.assertEqual("rejected", report.document["status"])
        self.assertEqual("rejected", entry["status"])
        self.assertGreater(entry["failed_tick_count"], 0)
        self.assertIsInstance(entry["first_failure_tick"], int)

    def test_identity_inventory_and_report_tamper_fail_closed(self):
        mesh, target = exact_mesh_and_target(converted=True)
        instance = calf_bend_instance(target, angle=15.0)
        report = build_motion_mesh_regression(instance, target.document, mesh)
        with self.assertRaises(MotionMeshRegressionError):
            build_motion_mesh_regression(
                instance, target.document,
                replace(mesh, bundle_sha256="f" * 64),
            )
        missing = replace(
            mesh,
            _document_json_items=tuple(
                (name, encoded({**json.loads(value), "attachments": []})
                 if name == "rig.json" else value)
                for name, value in mesh._document_json_items
            ),
        )
        with self.assertRaises(MotionMeshRegressionError):
            build_motion_mesh_regression(instance, target.document, missing)
        changed = report.document
        changed["status"] = "passed" if changed["status"] == "rejected" else "rejected"
        with self.assertRaises(MotionMeshRegressionError):
            require_motion_mesh_regression(
                changed, instance=instance,
                target_profile=target.document, verified_mesh=mesh,
            )


if __name__ == "__main__":
    unittest.main()
