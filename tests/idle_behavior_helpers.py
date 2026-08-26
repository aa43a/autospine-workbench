"""Shared exact full-chain fixture for P10.0 candidate tests."""

from __future__ import annotations

from pathlib import Path

from autospine_workbench.depth_order_candidates import (
    compile_depth_order_candidates,
)
from autospine_workbench.depth_order_inputs import require_depth_order_inputs
from autospine_workbench.foot_lock_candidate import compile_foot_lock_candidates
from autospine_workbench.mesh_bundle_contract import build_mesh_bundle_contract
from autospine_workbench.mesh_bundle_integrity import VerifiedMeshBundle
from autospine_workbench.mesh_probe_report import build_mesh_probe_report
from autospine_workbench.mesh_visual_artifacts import renderer_identities
from autospine_workbench.motion_instance_v2_compiler import (
    compile_motion_instance_v2,
)
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.motion_mesh_regression import build_motion_mesh_regression
from autospine_workbench.motion_policy_decision import build_motion_policy_decision
from autospine_workbench.motion_retarget_bundle_contract import (
    build_motion_retarget_bundle_contract,
)
from autospine_workbench.motion_retarget_bundle_integrity import (
    VerifiedMotionRetargetBundle,
)
from autospine_workbench.motion_retarget_compiler import compile_motion_instance
from autospine_workbench.motion_retarget_report import build_motion_retarget_report
from autospine_workbench.motion_target_profile import compile_motion_target_profile
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.reviewed_motion_bundle_contract import (
    build_reviewed_motion_bundle_contract,
)
from autospine_workbench.reviewed_motion_bundle_upstream import (
    require_reviewed_motion_upstreams,
)
from autospine_workbench.reviewed_motion_policy import (
    compile_reviewed_motion_policy,
)
from tests.depth_order_helpers import DepthOrderFixture
from tests.motion_policy_decision_helpers import approved_review
from tests.test_motion_target_profile import ik_fixture


class IdleBehaviorFixture:
    """Construct matching Layer Manifest/P3/P5/P8/P9 snapshots in memory."""

    def __init__(self, root: Path) -> None:
        seed = DepthOrderFixture(Path(root) / "seed")
        motion = VerifiedMotionBundleReader(Path(root) / "seed" / "state").load(
            seed.projected.p7_motion_sha256, seed.projected.p7_bundle_sha256
        )
        self.manifest = _manifest(seed.mesh.project_id)
        self.mesh = _mesh(seed.mesh, self.manifest, Path(root))
        self.retarget = _retarget(motion, self.mesh, Path(root))
        inputs = require_depth_order_inputs(
            seed.projected, self.retarget, self.mesh
        )
        depth = compile_depth_order_candidates(
            seed.projected, self.retarget, self.mesh, seed.policy(inputs)
        ).document
        foot = compile_foot_lock_candidates(
            seed.projected, self.retarget,
            max_correction_reference_ratio=10.0,
            max_residual_px=1_000_000.0,
        ).document
        candidate_ids = []
        from autospine_workbench.motion_policy_candidate_inventory import (
            derive_motion_policy_candidates,
        )
        for candidate in derive_motion_policy_candidates(foot, depth).candidates:
            candidate_ids.append({
                "candidate_id": candidate.candidate_id,
                "action": "accept", "reason_code": "human-reviewed",
                "payload": None,
            })
        decision = build_motion_policy_decision(
            foot, depth, review=approved_review(), decisions=candidate_ids,
            root_release_keys=[],
            draw_order_loop_reset={"mode": "explicit", "approved": False},
        ).document
        policy = compile_reviewed_motion_policy(
            decision, foot, depth, self.mesh
        ).document
        base, target = require_reviewed_motion_upstreams(
            self.mesh, self.retarget
        )
        v2 = compile_motion_instance_v2(base, target, policy).document
        self.reviewed = build_reviewed_motion_bundle_contract(
            self.mesh.project_id, foot, depth, decision, policy, v2,
            self.mesh, base, target,
        )


def _mesh(seed: VerifiedMeshBundle, manifest: dict, root: Path):
    rig, run = seed.rig, seed.run_manifest
    manifest_sha = canonical_sha256(manifest)
    run["inputs"]["layer_manifest_sha256"] = manifest_sha
    rig["source"]["layer_manifest_sha256"] = manifest_sha
    rig["source"]["run_manifest_sha256"] = canonical_sha256(run)
    rig["slots"].extend(_extra_slots())
    rig["attachments"].extend(_extra_attachments())
    rig["skins"]["default"].update({
        "hair": ["hair-image"], "mouth": ["mouth-image"],
    })
    probes = build_mesh_probe_report(rig, run, ()).document
    visuals = {
        "format": "autospine-mesh-visual-artifacts", "format_version": 1,
        "project_id": seed.project_id,
        "source": {
            "rig_sha256": canonical_sha256(rig),
            "run_manifest_sha256": canonical_sha256(run),
            "probes_sha256": canonical_sha256(probes),
        },
        "renderers": renderer_identities(), "status": "passed",
        "summary": "reviewed-noop", "images": [], "targets": [],
        "artifacts": [],
    }
    contract = build_mesh_bundle_contract(
        seed.project_id, rig, run, probes, visuals, {}
    )
    inputs = run["inputs"]
    return VerifiedMeshBundle(
        path=root / "p3", project_id=contract.project_id,
        rig_sha256=contract.rig_sha256, run_sha256=contract.run_sha256,
        probes_sha256=contract.probes_sha256,
        visuals_sha256=contract.visuals_sha256,
        bundle_sha256=contract.bundle_sha256,
        base_rig_sha256=inputs["base_rig_sha256"],
        base_bundle_sha256=inputs["base_bundle_sha256"],
        layer_manifest_sha256=inputs["layer_manifest_sha256"],
        resolved_project_sha256=inputs["resolved_project_sha256"],
        _document_json_items=tuple(
            (name, data.decode("utf-8"))
            for name, data in contract.document_bytes.items()
        ),
        _png_items=(),
    )


def _retarget(motion, mesh, root: Path):
    target_value = compile_motion_target_profile(ik_fixture(mesh), mesh)
    target = target_value.document
    compiled = compile_motion_instance(motion, target_value)
    report = build_motion_retarget_report(
        motion, target_value, compiled
    ).document
    mesh_report = build_motion_mesh_regression(
        compiled.instance, target, mesh
    ).document
    contract = build_motion_retarget_bundle_contract(
        mesh.project_id, target, compiled.instance, compiled.run,
        report, mesh_report,
    )
    source = {
        "p3_rig_sha256": target["source"]["p3"]["rig_sha256"],
        "p3_bundle_sha256": target["source"]["p3"]["bundle_sha256"],
        "p4_profile_sha256": target["source"]["p4_profile_sha256"],
        "p4_bundle_sha256": target["source"]["p4_bundle_sha256"],
        "motion_clip_sha256": compiled.instance["source"]["motion_ir_sha256"],
        "motion_bundle_sha256": compiled.instance["source"]["motion_bundle_sha256"],
    }
    return VerifiedMotionRetargetBundle(
        path=root / "p5", project_id=contract.project_id,
        clip_id=contract.clip_id,
        target_profile_sha256=contract.target_profile_sha256,
        instance_sha256=contract.instance_sha256,
        run_document_sha256=contract.run_document_sha256,
        retarget_report_sha256=contract.report_sha256,
        mesh_regression_sha256=contract.mesh_report_sha256,
        bundle_sha256=contract.bundle_sha256,
        _source_items=tuple(source.items()),
        _document_items=tuple(contract.document_bytes.items()),
    )


def _manifest(project_id: str) -> dict:
    return {
        "format": "autospine-layer-manifest", "format_version": 1,
        "project_id": project_id, "revision": 1,
        "source": {
            "psd_sha256": "a" * 64, "audit_sha256": "b" * 64,
            "canvas": [400, 400],
            "coordinate_system": {
                "origin": "top_left", "x_axis": "right", "y_axis": "down",
                "units": "pixel", "side_naming": "character_side",
                "view_orientation": "front", "mirror_state": "not_mirrored",
            },
        },
        "layers": [
            _layer("face-layer", "face.eyelash", "center", "4", "neck-head", 1),
            _layer("leg-layer", "body.leg.upper", "left", "5", "thigh.left", 0),
            _layer("hair-layer", "hair.front", "center", "6", "neck-head", 2),
            _layer("mouth-layer", "face.mouth", "center", "7", "neck-head", 3),
        ],
        "qa": {"status": "passed", "flags": [], "notes": []},
    }


def _layer(layer_id, role, side, sha_digit, bone, order):
    size = [20, 30]
    return {
        "layer_id": layer_id,
        "source": {"name": layer_id, "index": order, "group_path": [],
                   "visible": True, "opacity": 1.0, "blend_mode": "normal"},
        "raster": {"artifact_path": f"layers/{layer_id}.png",
                   "sha256": sha_digit * 64, "canvas_size": [400, 400],
                   "crop_bbox_xywh": [10 + order * 20, 20, *size],
                   "canvas_offset_xy": [10 + order * 20, 20],
                   "channels": "RGBA", "alpha_mode": "straight",
                   "color_space": "srgb", "alpha_nonzero": 600},
        "semantic": {"source_tag": layer_id, "canonical_role": role,
                     "side": side, "stratum": "front", "instance": 0,
                     "mapping_method": "manual", "confidence": 1.0},
        "derivation": {"operation": "source", "parent_layer_ids": []},
        "rig_hint": {"attachment_kind": "region", "deform_class": "face",
                     "candidate_bone": bone,
                     "pivot": {"xy": [20, 30], "method": "manual", "confidence": 1.0},
                     "setup_draw_order": order},
        "qa": {"status": "passed", "flags": [], "notes": []},
    }


def _extra_slots():
    return [
        {"id": "hair", "bone": "neck-head", "setup_attachment": "hair-image",
         "setup_draw_order": 2, "blend": "normal", "color_rgba": "ffffffff"},
        {"id": "mouth", "bone": "neck-head", "setup_attachment": "mouth-image",
         "setup_draw_order": 3, "blend": "normal", "color_rgba": "ffffffff"},
    ]


def _extra_attachments():
    return [
        {"id": f"{name}-image", "slot": name, "type": "region",
         "image_path": f"layers/{name}.png", "image_sha256": digit * 64,
         "source_layer_ids": [f"{name}-layer"], "canvas_offset_xy": [10, 20],
         "pivot_xy": [10, 15], "size": [20, 30]}
        for name, digit in (("hair", "6"), ("mouth", "7"))
    ]
