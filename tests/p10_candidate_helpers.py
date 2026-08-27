"""Persisted exact P3/P5/P9 fixture for P10 command tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

from autospine_workbench.ik_bundle_store import IkBundleStore
from autospine_workbench.ik_pipeline import VerifiedIkPipeline
from autospine_workbench.layer_manifest import LayerManifestBundleStore
from autospine_workbench.mesh_bundle_reader import VerifiedMeshBundleReader
from autospine_workbench.mesh_bundle_store import MeshBundleStore
from autospine_workbench.mesh_pipeline import VerifiedMeshPipeline
from autospine_workbench.motion_builtin import build_builtin_motion
from autospine_workbench.motion_bundle_store import MotionBundleStore
from autospine_workbench.motion_compile_run import build_builtin_motion_compile_run
from autospine_workbench.motion_retarget_bundle_reader import (
    VerifiedMotionRetargetBundleReader,
)
from autospine_workbench.motion_retarget_bundle_store import (
    MotionRetargetBundleStore,
)
from autospine_workbench.motion_retarget_pipeline import (
    VerifiedMotionRetargetPipeline,
)
from autospine_workbench.png_rgba import RgbaImage, encode_rgba_png
from autospine_workbench.region_rig import compile_region_rig
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.reviewed_motion_bundle_reader import (
    VerifiedReviewedMotionBundleReader,
)
from autospine_workbench.reviewed_motion_bundle_store import (
    ReviewedMotionBundleStore,
)
from autospine_workbench.rig_bundle import RigBundleStore
from tests.p10_candidate_documents import build_reviewed_documents
from tests.p9_v2_real_chain import _resolved
from tests.resolved_snapshot_helpers import (
    resolved_bone,
    resolved_joint,
    resolved_snapshot_from_parts,
)
from tests.test_verified_mesh_compiler import _probes


PROJECT = "p10-persisted"


class P10PersistedFixture:
    """Publish an integrated exact-reader chain with four setup regions."""

    def __init__(self, root: Path) -> None:
        root = Path(root)
        self.state = root / "state"
        asset = root / "layer.png"
        asset.write_bytes(encode_rgba_png(RgbaImage(
            20, 30, bytes((40, 80, 120, 255)) * 600,
        )))
        manifest = _manifest(asset)
        compiled = compile_region_rig(
            manifest,
            _resolved_for_project(),
            layer_manifest_sha256=canonical_sha256(manifest),
            image_sizes={row["layer_id"]: (20, 30)
                         for row in manifest["layers"]},
        )
        layer_paths = {row["layer_id"]: asset for row in manifest["layers"]}
        layers, self.layer_manifest_sha256 = LayerManifestBundleStore(
            self.state
        ).publish(PROJECT, manifest, layer_paths)
        rig_path, rig_sha = RigBundleStore(self.state).publish(
            PROJECT,
            compiled.rig,
            compiled.run_manifest,
            _probes(PROJECT, compiled.rig, compiled.run_manifest),
            layers,
        )
        mesh_result = VerifiedMeshPipeline(self.state).build(
            PROJECT, rig_sha, rig_path.name
        )
        mesh_address = MeshBundleStore(self.state).publish(
            PROJECT,
            mesh_result.rig,
            mesh_result.run_manifest,
            mesh_result.probes,
            mesh_result.visuals,
            mesh_result.pngs,
        )
        self.mesh = VerifiedMeshBundleReader(self.state).load(
            PROJECT, mesh_address.rig_sha256, mesh_address.bundle_sha256
        )
        self.retarget = _publish_p5(self.state, self.mesh)
        documents = build_reviewed_documents(self.mesh, self.retarget)
        published = ReviewedMotionBundleStore(self.state).publish(
            PROJECT, *documents, self.mesh, self.retarget
        )
        self.reviewed = VerifiedReviewedMotionBundleReader(self.state).load(
            PROJECT,
            published.motion_instance_v2_sha256,
            published.bundle_sha256,
            mesh_bundle=self.mesh,
            retarget_bundle=self.retarget,
        )

    @property
    def command_kwargs(self) -> dict[str, str]:
        return {
            "layer_manifest_sha256": self.layer_manifest_sha256,
            "p3_rig_sha256": self.mesh.rig_sha256,
            "p3_bundle_sha256": self.mesh.bundle_sha256,
            "motion_instance_sha256": self.retarget.instance_sha256,
            "motion_retarget_bundle_sha256": self.retarget.bundle_sha256,
            "motion_instance_v2_sha256": (
                self.reviewed.motion_instance_v2_sha256
            ),
            "reviewed_motion_bundle_sha256": self.reviewed.bundle_sha256,
        }


def _publish_p5(state: Path, mesh):
    ik = VerifiedIkPipeline(state).build(
        PROJECT, mesh.rig_sha256, mesh.bundle_sha256
    )
    ik_address = IkBundleStore(state).publish(PROJECT, ik.profile, ik.probes)
    motion = build_builtin_motion("idle")
    run = build_builtin_motion_compile_run("idle", motion.document)
    motion_address = MotionBundleStore(state).publish(
        motion.document, run.document
    )
    result = VerifiedMotionRetargetPipeline(state).build(
        PROJECT,
        mesh.rig_sha256,
        mesh.bundle_sha256,
        ik_address.profile_sha256,
        ik_address.bundle_sha256,
        motion_address.clip_sha256,
        motion_address.bundle_sha256,
    )
    address = MotionRetargetBundleStore(state).publish(
        PROJECT,
        result.target_profile,
        result.motion_instance,
        result.retarget_run,
        result.retarget_report,
        result.mesh_regression,
    )
    return VerifiedMotionRetargetBundleReader(state).load(
        PROJECT, address.instance_sha256, address.bundle_sha256
    )


def _manifest(asset: Path):
    digest = hashlib.sha256(asset.read_bytes()).hexdigest()
    specs = (
        ("face-layer", "face.eyelash", "neck-head", 0, (180, 20)),
        ("mouth-layer", "face.mouth", "neck-head", 1, (180, 55)),
        ("hair-layer", "hair.front", "neck-head", 2, (160, 15)),
        ("torso-layer", "body.torso", "spine-chest", 3, (185, 100)),
    )
    layers = []
    for layer_id, role, bone, order, offset in specs:
        layers.append(_layer(layer_id, role, bone, order, offset, digest))
    return {
        "format": "autospine-layer-manifest",
        "format_version": 1,
        "project_id": PROJECT,
        "revision": 1,
        "source": {
            "psd_sha256": "a" * 64,
            "audit_sha256": "b" * 64,
            "canvas": [400, 400],
            "coordinate_system": {
                "origin": "top_left",
                "x_axis": "right",
                "y_axis": "down",
                "units": "pixel",
                "side_naming": "character_side",
                "view_orientation": "front",
                "mirror_state": "not_mirrored",
            },
        },
        "layers": layers,
        "qa": {"status": "passed", "flags": [], "notes": []},
    }


def _layer(layer_id, role, bone, order, offset, digest):
    return {
        "layer_id": layer_id,
        "source": {
            "name": layer_id,
            "index": order,
            "group_path": [],
            "visible": True,
            "opacity": 1.0,
            "blend_mode": "normal",
        },
        "raster": {
            "artifact_path": f"layers/{layer_id}.png",
            "sha256": digest,
            "canvas_size": [400, 400],
            "crop_bbox_xywh": [offset[0], offset[1], 20, 30],
            "canvas_offset_xy": list(offset),
            "channels": "RGBA",
            "alpha_mode": "straight",
            "color_space": "srgb",
            "alpha_nonzero": 600,
        },
        "semantic": {
            "source_tag": layer_id,
            "canonical_role": role,
            "side": "center",
            "stratum": "front",
            "instance": 0,
            "mapping_method": "manual",
            "confidence": 1.0,
        },
        "derivation": {"operation": "source", "parent_layer_ids": []},
        "rig_hint": {
            "attachment_kind": "region",
            "deform_class": "rigid",
            "candidate_bone": bone,
            "pivot": {
                "xy": [offset[0] + 10, offset[1] + 15],
                "method": "manual",
                "confidence": 1.0,
            },
            "setup_draw_order": order,
        },
        "qa": {"status": "passed", "flags": [], "notes": []},
    }


def _resolved_for_project():
    legacy = _resolved()
    source_joints = {
        joint["id"]: joint for joint in legacy["skeleton"]["joints"]
    }
    source_bones = legacy["skeleton"]["bones"]
    end_joint_by_bone = {
        bone["id"]: bone["end_joint_id"] for bone in source_bones
    }
    joints_by_id = {}
    bones = []
    for bone in source_bones:
        parent_id = bone["parent_id"]
        source_start_id = bone["start_joint_id"]
        start_joint_id = (
            source_start_id
            if parent_id is None
            else end_joint_by_bone[parent_id]
        )
        end_joint_id = bone["end_joint_id"]
        for joint_id, source_id in (
            (start_joint_id, source_start_id),
            (end_joint_id, end_joint_id),
        ):
            if joint_id in joints_by_id:
                continue
            source = source_joints[source_id]
            side = (
                "left" if ".left" in joint_id
                else "right" if ".right" in joint_id
                else "center"
            )
            joints_by_id[joint_id] = resolved_joint(
                joint_id,
                side=side,
                x=source["x"],
                # The shared P9 strict fixture already applies the one rigid
                # y-translation needed to fit the declared canvas.
                y=source["y"],
                revision=1,
            )
        bones.append(resolved_bone(
            bone["id"],
            parent_id=parent_id,
            start_joint_id=start_joint_id,
            end_joint_id=end_joint_id,
            role=f"humanoid.{bone['id']}",
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
