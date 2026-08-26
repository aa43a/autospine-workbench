"""Fail-closed availability rules for candidate-only idle behaviors."""

from __future__ import annotations

import json
import re
from typing import Any

from .idle_behavior_candidate_identity import body_sway_candidate_id
from .idle_behavior_candidate_validation import (
    BODY_SWAY_PROPOSAL,
    FEATURE_ORDER,
    GENERATOR,
)
from .idle_behavior_inventory import IdleBehaviorInventory


_SHA = re.compile(r"^[0-9a-f]{64}$")


class IdleBehaviorRuleError(ValueError):
    """Raised when an internal evidence inventory is incomplete or unsafe."""


def classify_idle_behavior_features(
    inventory: IdleBehaviorInventory,
    *,
    motion_instance_v2_sha256: str,
    target_profile_sha256: str,
) -> list[dict[str, Any]]:
    """Classify all four features without emitting decisions or timelines."""

    if type(inventory) is not IdleBehaviorInventory:
        raise IdleBehaviorRuleError("Idle behavior inventory type is invalid")
    if not isinstance(motion_instance_v2_sha256, str) \
            or not _SHA.fullmatch(motion_instance_v2_sha256) \
            or not isinstance(target_profile_sha256, str) \
            or not _SHA.fullmatch(target_profile_sha256):
        raise IdleBehaviorRuleError("Idle behavior source SHA is invalid")
    document = inventory.document
    rows = document.get("features")
    target_inventory = document.get("target_inventory")
    if not isinstance(rows, dict) or set(rows) != set(FEATURE_ORDER) \
            or not isinstance(target_inventory, list):
        raise IdleBehaviorRuleError("Idle behavior evidence inventory is invalid")
    result = []
    for feature_id in FEATURE_ORDER:
        evidence = rows[feature_id]
        if not isinstance(evidence, dict) or not isinstance(
                evidence.get("evidence"), dict):
            raise IdleBehaviorRuleError("Idle behavior feature evidence is invalid")
        availability, reasons = _availability(feature_id, evidence)
        candidate_id = None
        proposal = None
        if availability == "candidate":
            candidate_id = body_sway_candidate_id(
                generator=GENERATOR,
                motion_instance_v2_sha256=motion_instance_v2_sha256,
                target_profile_sha256=target_profile_sha256,
                feature_id=feature_id,
                target_bone_ids=BODY_SWAY_PROPOSAL["target_bone_ids"],
            )
            proposal = json.loads(json.dumps(BODY_SWAY_PROPOSAL))
        result.append({
            "feature_id": feature_id,
            "availability": availability,
            "candidate_id": candidate_id,
            "evidence": json.loads(json.dumps(evidence["evidence"])),
            "reason_codes": sorted(set(reasons)),
            "proposal": proposal,
        })
    return result


def _availability(feature_id: str, row: dict[str, Any]):
    if feature_id == "body_sway":
        if row.get("body_chain_complete") is True:
            return "candidate", (
                "additive_rotation_overlay_unimplemented",
                "human_parameters_required",
                "runtime_timeline_not_emitted",
                "torso_safe_range_unprobed",
            )
        return "unobservable", ("canonical_body_chain_incomplete",)
    if feature_id == "blink":
        return "unobservable", _visual_state_reasons(
            row, missing="eye_setup_layer_missing",
            state="blink_visual_states_unobserved",
        )
    if feature_id == "mouth":
        return "unobservable", _visual_state_reasons(
            row, missing="mouth_setup_layer_missing",
            state="viseme_visual_states_unobserved",
        )
    if not row.get("has_layers"):
        return "unobservable", ("hair_setup_layer_missing",)
    if not row.get("all_layers_reviewed"):
        return "unobservable", ("hair_semantic_review_required",)
    if not row.get("all_layers_bound"):
        return "unobservable", ("hair_setup_binding_unobservable",)
    reasons = ["independent_hair_dof_missing", "physics_unsupported"]
    reasons.append(
        "hair_deform_runtime_unsupported"
        if row.get("hair_mesh_present") else "hair_mesh_missing"
    )
    return "unsupported", tuple(reasons)


def _visual_state_reasons(row, *, missing: str, state: str):
    if not row.get("has_layers"):
        return ("attachment_switching_unsupported", missing, state)
    reasons = [
        "attachment_switching_unsupported", state,
        "single_setup_state_is_not_runtime_state_evidence",
    ]
    if not row.get("all_layers_reviewed"):
        reasons.append("semantic_review_required")
    if not row.get("all_layers_bound"):
        reasons.append("setup_binding_unobservable")
    return tuple(reasons)
