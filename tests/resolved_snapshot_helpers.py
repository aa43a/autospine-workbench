"""Complete canonical fixtures for the public resolved snapshot v1 contract."""

from __future__ import annotations

from copy import deepcopy

from autospine_workbench.resolved_project import canonical_sha256


PROJECT_ID = "sample-a"
REVISION = 3


def resolved_snapshot_fixture() -> dict:
    split_spec = {
        "parts": {
            "left": {
                "guide": [
                    {"kind": "joint", "joint_id": "hip.left"},
                    {"kind": "joint", "joint_id": "knee.left"},
                    {"kind": "joint", "joint_id": "ankle.left"},
                ],
                "pivot": {"kind": "joint", "joint_id": "hip.left"},
                "candidate_bone": "thigh.left",
            },
            "right": {
                "guide": [
                    {"kind": "joint", "joint_id": "hip.right"},
                    {"kind": "joint", "joint_id": "knee.right"},
                    {"kind": "joint", "joint_id": "ankle.right"},
                ],
                "pivot": {"kind": "joint", "joint_id": "hip.right"},
                "candidate_bone": "thigh.right",
            },
        }
    }
    layers = [
        _layer(
            "layer-000-torso", 0, "body.torso", "center",
            [50, 50, 100, 160], [100.0, 100.0], "root-pelvis",
        ),
        {
            **_layer(
                "layer-001-legwear", 1, "body.leg", "bilateral",
                [60, 190, 80, 100], [100.0, 210.0], None,
            ),
            "disposition": "split_left_right",
            "reviewed_fields": ["canonical_role", "side", "disposition", "visible"],
            "split_spec": split_spec,
            "split_spec_revision": REVISION,
            "split_decision": {
                "action": "accept",
                "split_artifact_sha256": "1" * 64,
                "operation_config_sha256": "2" * 64,
                "review_target_sha256": "3" * 64,
                "analysis": {
                    "layer_manifest_sha256": "4" * 64,
                    "resolved_snapshot_sha256": "5" * 64,
                    "split_spec_sha256": canonical_sha256(split_spec),
                    "algorithm_id": "nearest-limb-polyline",
                    "algorithm_version": "1.2.0",
                },
                "binding_status": "current",
            },
            "split_decision_revision": REVISION,
        },
    ]
    joints = [
        _joint("root", "center", 100, 290),
        _joint("pelvis", "center", 100, 200),
        _joint("hip.left", "left", 120, 210),
        _joint("knee.left", "left", 130, 250),
        _joint("ankle.left", "left", 140, 290),
        _joint("hip.right", "right", 80, 210),
        _joint("knee.right", "right", 70, 250),
        _joint("ankle.right", "right", 60, 290),
    ]
    bones = [
        _bone("root-pelvis", None, "root", "pelvis", "humanoid.root"),
        _bone("pelvis-hip.left", "root-pelvis", "pelvis", "hip.left", "humanoid.hip.left"),
        _bone("thigh.left", "pelvis-hip.left", "hip.left", "knee.left", "humanoid.leg.upper.left"),
        _bone("calf.left", "thigh.left", "knee.left", "ankle.left", "humanoid.leg.lower.left"),
        _bone("pelvis-hip.right", "root-pelvis", "pelvis", "hip.right", "humanoid.hip.right"),
        _bone("thigh.right", "pelvis-hip.right", "hip.right", "knee.right", "humanoid.leg.upper.right"),
        _bone("calf.right", "thigh.right", "knee.right", "ankle.right", "humanoid.leg.lower.right"),
    ]
    document = {
        "schema_version": "autospine.resolved-project/v1",
        "project_id": PROJECT_ID,
        "revision": REVISION,
        "inputs": {
            "base_project_sha256": "a" * 64,
            "override_sha256": "b" * 64,
            "candidate_analyses": [],
        },
        "canvas": {
            "width": 200,
            "height": 300,
            "coordinate_system": "canvas-top-left-y-down",
        },
        "layers": layers,
        "skeleton": {
            "schema_version": "autospine-workbench.skeleton/v1",
            "contract": {"name": "autospine-workbench.skeleton", "version": 1},
            "template": "humanoid-v1",
            "coordinate_system": {
                "origin": "canvas-top-left",
                "x_axis": "right",
                "y_axis": "down",
                "side_semantics": "character-own-left-right",
            },
            "generation": {"method": "fixture-v1", "requires_review": True},
            "joints": joints,
            "bones": bones,
        },
        "qa": {
            "status": "ready",
            "review_layer_ids": [],
            "unresolved_joint_ids": [],
            "rejected_joint_ids": [],
            "unobservable_joint_ids": [],
            "accepted_split_layer_ids": ["layer-001-legwear"],
            "unreviewed_split_layer_ids": [],
            "rejected_split_layer_ids": [],
            "stale_split_layer_ids": [],
        },
    }
    return reseal(document)


def with_candidate_accept(document: dict, joint_id: str = "knee.left") -> dict:
    result = deepcopy(document)
    joint = next(item for item in result["skeleton"]["joints"] if item["id"] == joint_id)
    analysis = {
        "provider": "fixture-provider",
        "provider_version": "2.0.0",
        "input_sha256": "6" * 64,
        "config_sha256": "7" * 64,
    }
    analysis["run_sha256"] = canonical_sha256(analysis)
    artifact = "8" * 64
    joint.update(
        review_state="candidate_accepted",
        decision_kind="candidate_accept",
        decision_revision=result["revision"],
        decision={
            "action": "accept",
            "candidate_artifact_sha256": artifact,
            "candidate_id": f"{joint_id}.pose.0123456789ab",
            "final_xy": [float(joint["x"]), float(joint["y"])],
            "analysis": deepcopy(analysis),
        },
    )
    result["inputs"]["candidate_analyses"] = [
        {"candidate_artifact_sha256": artifact, **analysis}
    ]
    return reseal(result)


def reseal(document: dict) -> dict:
    result = deepcopy(document)
    result.pop("sha256", None)
    result["sha256"] = canonical_sha256(result)
    return result


def _layer(
    layer_id: str,
    index: int,
    canonical_role: str,
    side: str,
    bbox: list[int],
    pivot: list[float],
    candidate_bone: str | None,
) -> dict:
    x, y, width, height = bbox
    reviewed = ["canonical_role", "side", "disposition", "visible", "pivot_xy"]
    layer = {
        "schema_version": "autospine-workbench.layer/v1",
        "contract": {"name": "autospine-workbench.layer", "version": 1},
        "id": layer_id,
        "source_index": index,
        "name": layer_id,
        "canonical_role": canonical_role,
        "side": side,
        "disposition": "keep",
        "visible": True,
        "empty": False,
        "opacity": 1.0,
        "blend_mode": "BlendMode.NORMAL",
        "z_index": index,
        "bbox": {
            "x": x, "y": y, "width": width, "height": height,
            "right": x + width, "bottom": y + height,
        },
        "pivot_xy": pivot,
        "image_url": f"/api/projects/{PROJECT_ID}/layers/{layer_id}/image",
        "metrics": {
            "alpha_nonzero": width * height,
            "alpha_perceptible": width * height,
            "component_count": 1,
            "main_component_ratio": 1.0,
            "fills_bbox_ratio": 1.0,
        },
        "review_state": "manual_adjusted",
        "reviewed_fields": reviewed,
        "decision_revision": REVISION,
    }
    if candidate_bone is not None:
        layer["candidate_bone"] = candidate_bone
        reviewed.append("candidate_bone")
    return layer


def _joint(joint_id: str, side: str, x: float, y: float) -> dict:
    return {
        "id": joint_id,
        "role": f"humanoid.{joint_id}",
        "side": side,
        "x": x,
        "y": y,
        "confidence": 0.75,
        "source": "fixture",
        "editable": True,
        "model_confidence": 0.75,
        "review_state": "manual_adjusted",
        "decision_kind": "manual_absolute",
        "decision_revision": REVISION,
    }


def _bone(bone_id: str, parent: str | None, start: str, end: str, role: str) -> dict:
    return {
        "id": bone_id,
        "role": role,
        "parent_id": parent,
        "start_joint_id": start,
        "end_joint_id": end,
    }
