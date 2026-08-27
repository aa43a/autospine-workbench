"""Real persisted full-humanoid source chain for P9.5 CLI tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from autospine_workbench.ik_bundle_store import IkBundleStore
from autospine_workbench.ik_pipeline import VerifiedIkPipeline
from autospine_workbench.layer_manifest import LayerManifestBundleStore
from autospine_workbench.mesh_bundle_store import MeshBundleStore
from autospine_workbench.mesh_pipeline import VerifiedMeshPipeline
from autospine_workbench.motion_builtin import build_builtin_motion
from autospine_workbench.motion_bundle_store import MotionBundleStore
from autospine_workbench.motion_compile_run import build_builtin_motion_compile_run
from autospine_workbench.motion_retarget_bundle_store import (
    MotionRetargetBundleStore,
)
from autospine_workbench.motion_retarget_pipeline import (
    VerifiedMotionRetargetPipeline,
)
from autospine_workbench.png_rgba import RgbaImage, encode_rgba_png
from autospine_workbench.region_rig import compile_region_rig
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.reviewed_motion_policy_validation import SEMANTICS
from autospine_workbench.rig_bundle import RigBundleStore
from autospine_workbench.rig_fk import evaluate_world_setup
from tests.resolved_snapshot_helpers import (
    resolved_bone,
    resolved_joint,
    resolved_snapshot_from_parts,
)
from tests.test_motion_target_profile import full_rig
from tests.test_verified_mesh_compiler import _probes


PROJECT = "p9-v2-real"


class P9V2RealFixture:
    """Publish a complete full-humanoid P2/P3/P4/Motion/P5 chain."""

    def __init__(self, root: Path) -> None:
        root = Path(root)
        self.state = root / "state"
        asset = root / "face-layer.png"
        asset.write_bytes(encode_rgba_png(RgbaImage(
            20, 30, bytes((40, 80, 120, 255)) * 600,
        )))
        manifest, resolved = _manifest(asset), _resolved()
        compiled = compile_region_rig(
            manifest, resolved,
            layer_manifest_sha256=canonical_sha256(manifest),
            image_sizes={"face-layer": (20, 30)},
        )
        layers, _manifest_sha = LayerManifestBundleStore(self.state).publish(
            PROJECT, manifest, {"face-layer": asset}
        )
        rig_path, rig_sha = RigBundleStore(self.state).publish(
            PROJECT, compiled.rig, compiled.run_manifest,
            _probes(PROJECT, compiled.rig, compiled.run_manifest), layers,
        )
        mesh = VerifiedMeshPipeline(self.state).build(
            PROJECT, rig_sha, rig_path.name
        )
        mesh_address = MeshBundleStore(self.state).publish(
            PROJECT, mesh.rig, mesh.run_manifest,
            mesh.probes, mesh.visuals, mesh.pngs,
        )
        self.project_id = PROJECT
        self.p3_rig_sha256 = mesh_address.rig_sha256
        self.p3_bundle_sha256 = mesh_address.bundle_sha256
        ik = VerifiedIkPipeline(self.state).build(
            PROJECT, self.p3_rig_sha256, self.p3_bundle_sha256
        )
        ik_address = IkBundleStore(self.state).publish(
            PROJECT, ik.profile, ik.probes
        )
        motion = build_builtin_motion("idle")
        motion_run = build_builtin_motion_compile_run("idle", motion.document)
        motion_address = MotionBundleStore(self.state).publish(
            motion.document, motion_run.document
        )
        p5 = VerifiedMotionRetargetPipeline(self.state).build(
            PROJECT, self.p3_rig_sha256, self.p3_bundle_sha256,
            ik_address.profile_sha256, ik_address.bundle_sha256,
            motion_address.clip_sha256, motion_address.bundle_sha256,
        )
        self.p5_address = MotionRetargetBundleStore(self.state).publish(
            PROJECT, p5.target_profile, p5.motion_instance,
            p5.retarget_run, p5.retarget_report, p5.mesh_regression,
        )
        self.policy_path = root / "reviewed-policy-real.json"
        self.policy_path.write_text(
            json.dumps(
                _policy(p5, self.p5_address.bundle_sha256),
                ensure_ascii=False, allow_nan=False,
                sort_keys=True, separators=(",", ":"),
            ),
            encoding="utf-8",
        )


def _manifest(asset: Path) -> dict:
    return {
        "format": "autospine-layer-manifest", "format_version": 1,
        "project_id": PROJECT, "revision": 1,
        "source": {
            "psd_sha256": "a" * 64, "audit_sha256": "b" * 64,
            "canvas": [400, 400],
            "coordinate_system": {
                "origin": "top_left", "x_axis": "right", "y_axis": "down",
                "units": "pixel", "side_naming": "character_side",
                "view_orientation": "front", "mirror_state": "not_mirrored",
            },
        },
        "layers": [{
            "layer_id": "face-layer",
            "source": {
                "name": "face", "index": 0, "group_path": [], "visible": True,
                "opacity": 1.0, "blend_mode": "normal",
            },
            "raster": {
                "artifact_path": "layers/face-layer.png",
                "sha256": hashlib.sha256(asset.read_bytes()).hexdigest(),
                "canvas_size": [400, 400], "crop_bbox_xywh": [185, 20, 20, 30],
                "canvas_offset_xy": [185, 20], "channels": "RGBA",
                "alpha_mode": "straight", "color_space": "srgb",
                "alpha_nonzero": 600,
            },
            "semantic": {
                "source_tag": "face", "canonical_role": "body.head",
                "side": "center", "stratum": "face", "instance": 0,
                "mapping_method": "manual", "confidence": 1.0,
            },
            "derivation": {"operation": "source", "parent_layer_ids": []},
            "rig_hint": {
                "attachment_kind": "region", "deform_class": "rigid",
                "candidate_bone": "neck-head",
                "pivot": {"xy": [195, 35], "method": "manual", "confidence": 1.0},
                "setup_draw_order": 0,
            },
            "qa": {"status": "passed", "flags": [], "notes": []},
        }],
        "qa": {"status": "passed", "flags": [], "notes": []},
    }


def _resolved() -> dict:
    source_bones = full_rig()["bones"]
    world = evaluate_world_setup(source_bones)
    joints_by_id, bones = {}, []
    for bone in source_bones:
        bone_id, frame = bone["id"], world[bone["id"]]
        parent_id = bone["parent"]
        start_id = (
            f"{bone_id}.start"
            if parent_id is None
            else f"{parent_id}.end"
        )
        end_id = f"{bone_id}.end"
        for joint_id, point in (
            (start_id, frame["origin_xy"]),
            (end_id, frame["endpoint_xy"]),
        ):
            if joint_id in joints_by_id:
                continue
            side = (
                "left" if ".left" in joint_id
                else "right" if ".right" in joint_id
                else "center"
            )
            joint = resolved_joint(
                joint_id,
                side=side,
                x=point[0],
                # The source pose extends 37 px below the 400 px canvas.
                # Translating the whole setup keeps every local transform.
                y=point[1] - 40,
                revision=1,
            )
            joint["confidence"] = 1.0
            joint["model_confidence"] = 1.0
            joints_by_id[joint_id] = joint
        bones.append(resolved_bone(
            bone_id,
            parent_id=parent_id,
            start_joint_id=start_id,
            end_joint_id=end_id,
            role=f"humanoid.{bone_id}",
        ))
    return resolved_snapshot_from_parts(
        project_id=PROJECT,
        revision=1,
        width=400,
        height=400,
        layers=[],
        joints=list(joints_by_id.values()),
        bones=bones,
        base_project_sha256="c" * 64,
        override_sha256="d" * 64,
    )


def _policy(p5, bundle_sha: str) -> dict:
    instance, target = p5.motion_instance, p5.target_profile
    duration, setup = instance["timing"]["duration_ticks"], ["face-layer"]
    return {
        "format": "autospine-reviewed-motion-policy", "format_version": 1,
        "project_id": PROJECT, "clip_id": instance["clip_id"],
        "source": {
            "motion_policy_decision_sha256": "1" * 64,
            "foot_lock_candidates_sha256": "2" * 64,
            "depth_order_candidates_sha256": "3" * 64,
            "depth_pair_policy_sha256": "4" * 64,
            "p8": {field: value * 64 for field, value in (
                ("projected_motion_sha256", "5"), ("bundle_sha256", "6"),
                ("camera_sha256", "7"), ("run_sha256", "8"),
                ("legacy_motion_sha256", "9"), ("p7_motion_sha256", "a"),
                ("p7_bundle_sha256", "b"), ("p7_run_sha256", "c"),
            )},
            "p5": {
                "target_profile_sha256": canonical_sha256(target),
                "instance_sha256": canonical_sha256(instance),
                "run_sha256": canonical_sha256(p5.retarget_run),
                "retarget_report_sha256": canonical_sha256(p5.retarget_report),
                "mesh_regression_sha256": canonical_sha256(p5.mesh_regression),
                "bundle_sha256": bundle_sha,
            },
            "p3": target["source"]["p3"],
        },
        "timing": {**instance["timing"], "frame_count": 2},
        "semantics": dict(SEMANTICS),
        "root_correction_keys": [{
            "tick": tick, "correction_xy_px": [0.0, 0.0],
            "incoming_interpolation": "linear",
        } for tick in (0, duration)],
        "slot_order": {
            "setup_slot_ids": setup,
            "keys": [{"tick": 0, "slot_ids": setup}],
        },
    }
