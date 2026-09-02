"""Pure path-free source closure for BodySwayDynamicSeamProbe v2."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .body_sway_continuous_proof_validation_v2 import (
    BodySwayContinuousProofValidationV2Error,
    body_sway_continuous_preview_proof_sha256_v2,
)
from .body_sway_dynamic_seam_profile_v2 import (
    FORMAT,
    FORMAT_VERSION,
    MAX_CONTINUOUS_PROOF_V2_BYTES,
    MAX_REVIEWED_SET_V1_BYTES,
    MAX_SEAM_CANDIDATE_V1_BYTES,
    MAX_SEAM_DECISION_V1_BYTES,
    MAX_SOURCE_BYTES,
    MAX_SOURCE_JSON_DEPTH,
    MAX_SOURCE_JSON_NODES,
    body_sway_dynamic_seam_source_sha256_v2,
)
from .manifest_artifacts import LayerManifestError, require_sha256
from .resolved_project import canonical_sha256
from .reviewed_seam_anchor_set_bundle_contract import (
    ReviewedSeamAnchorSetBundleContractError,
    build_reviewed_seam_anchor_set_bundle_contract,
)
from .seam_anchor_review_json import (
    canonical_json_bytes,
    require_bounded_json_tree,
)


class BodySwayDynamicSeamSourceV2Error(ValueError):
    """Raised when v2 proof and reviewed v1 anchors do not cross-bind."""


def build_body_sway_dynamic_seam_source_v2(
    *,
    continuous_proof_v2: Mapping[str, Any],
    seam_anchor_candidates_v1: Mapping[str, Any],
    seam_anchor_review_decision_v1: Mapping[str, Any],
    reviewed_seam_anchor_set_v1: Mapping[str, Any],
    reviewed_set_v1_bundle_sha256: str,
) -> dict[str, Any]:
    """Validate and seal the exact mixed-version P10.5d input closure."""

    try:
        proof = _copy_object(
            continuous_proof_v2, "continuous proof v2",
            MAX_CONTINUOUS_PROOF_V2_BYTES,
        )
        candidates = _copy_object(
            seam_anchor_candidates_v1, "seam-anchor candidates v1",
            MAX_SEAM_CANDIDATE_V1_BYTES,
        )
        decision = _copy_object(
            seam_anchor_review_decision_v1,
            "seam-anchor review decision v1",
            MAX_SEAM_DECISION_V1_BYTES,
        )
        reviewed_set = _copy_object(
            reviewed_seam_anchor_set_v1, "reviewed seam-anchor set v1",
            MAX_REVIEWED_SET_V1_BYTES,
        )
        require_sha256(
            reviewed_set_v1_bundle_sha256,
            "Reviewed seam-anchor set v1 bundle digest",
        )
        proof_sha = body_sway_continuous_preview_proof_sha256_v2(proof)
        proof_source = proof["source"]
        rig = _proof_rig(proof_source)
        p3 = _proof_p3(proof_source)
        contract = build_reviewed_seam_anchor_set_bundle_contract(
            candidates, decision, rig, reviewed_set,
        )
        if contract.bundle_sha256 != reviewed_set_v1_bundle_sha256:
            raise BodySwayDynamicSeamSourceV2Error(
                "Reviewed seam-anchor set v1 bundle differs from exact replay"
            )
        _require_cross_chain(
            proof, proof_source, p3, candidates, decision,
            reviewed_set, contract,
        )
        source = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "project_id": proof["project_id"],
            "clip_id": proof["clip_id"],
            "layer_manifest_sha256": p3["layer_manifest_sha256"],
            "p3_rig_sha256": p3["rig_sha256"],
            "p3_bundle_sha256": p3["bundle_sha256"],
            "body_sway_continuous_preview_proof_v2_sha256": proof_sha,
            "body_sway_continuous_preview_proof_v2": proof,
            "seam_anchor_candidates_v1_sha256": contract.candidate_sha256,
            "seam_anchor_candidates_v1": candidates,
            "seam_anchor_review_decision_v1_sha256": contract.decision_sha256,
            "seam_anchor_review_decision_v1": decision,
            "review_revision": contract.review_revision,
            "reviewed_seam_anchor_set_v1_sha256": contract.set_sha256,
            "reviewed_seam_anchor_set_v1_bundle_sha256": contract.bundle_sha256,
            "reviewed_seam_anchor_set_v1": reviewed_set,
        }
        source["source_set_sha256"] = (
            body_sway_dynamic_seam_source_sha256_v2(source)
        )
        _require_source_budget(source)
        return source
    except BodySwayDynamicSeamSourceV2Error:
        raise
    except (
        AttributeError,
        BodySwayContinuousProofValidationV2Error,
        KeyError,
        LayerManifestError,
        OverflowError,
        RecursionError,
        ReviewedSeamAnchorSetBundleContractError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as exc:
        raise BodySwayDynamicSeamSourceV2Error(
            f"Dynamic seam source v2 admission failed: {exc}"
        ) from exc


def _proof_rig(proof_source: dict[str, Any]) -> dict[str, Any]:
    rig = proof_source["rig_ir"]
    if type(rig) is not dict \
            or canonical_sha256(rig) != proof_source["rig_ir_sha256"]:
        raise BodySwayDynamicSeamSourceV2Error(
            "Dynamic seam source v2 RigIR identity is inconsistent"
        )
    return rig


def _proof_p3(proof_source: dict[str, Any]) -> dict[str, Any]:
    p3 = proof_source["amplitude_envelope_candidate_v2"]["source"] \
        ["reviewed_probe_report"]["source"]["p3"]
    if type(p3) is not dict or any(
        key not in p3 for key in (
            "layer_manifest_sha256", "rig_sha256", "bundle_sha256",
        )
    ):
        raise BodySwayDynamicSeamSourceV2Error(
            "Dynamic seam source v2 P3 identity is incomplete"
        )
    return p3


def _require_cross_chain(
    proof, proof_source, p3, candidates, decision, reviewed_set, contract,
) -> None:
    project_id = proof["project_id"]
    if any(document.get("project_id") != project_id for document in (
        candidates, decision, reviewed_set,
    )) or contract.project_id != project_id:
        raise BodySwayDynamicSeamSourceV2Error(
            "Dynamic seam source v2 project identities are cross-wired"
        )
    p3_expected = {
        "layer_manifest_sha256": p3["layer_manifest_sha256"],
        "rig_sha256": p3["rig_sha256"],
        "bundle_sha256": p3["bundle_sha256"],
    }
    candidate_source = candidates["source"]
    if any(candidate_source[field] != value
           for field, value in p3_expected.items()) \
            or proof_source["rig_ir_sha256"] != p3_expected["rig_sha256"]:
        raise BodySwayDynamicSeamSourceV2Error(
            "Dynamic seam source v2 Manifest, P3, or RigIR is cross-wired"
        )
    expected_reviewed_source = {
        "layer_manifest_sha256": p3_expected["layer_manifest_sha256"],
        "p3_rig_sha256": p3_expected["rig_sha256"],
        "p3_bundle_sha256": p3_expected["bundle_sha256"],
        "seam_anchor_candidate_sha256": contract.candidate_sha256,
        "review_revision": contract.review_revision,
        "seam_anchor_review_decision_sha256": contract.decision_sha256,
    }
    if reviewed_set["source"] != expected_reviewed_source \
            or contract.set_sha256 != canonical_sha256(reviewed_set):
        raise BodySwayDynamicSeamSourceV2Error(
            "Dynamic seam source v2 reviewed-set provenance is cross-wired"
        )


def _copy_object(value: Any, label: str, byte_limit: int) -> dict[str, Any]:
    require_bounded_json_tree(
        value, max_nodes=MAX_SOURCE_JSON_NODES,
        max_depth=MAX_SOURCE_JSON_DEPTH,
    )
    encoded = canonical_json_bytes(value)
    if len(encoded) > byte_limit:
        raise BodySwayDynamicSeamSourceV2Error(
            f"Dynamic seam source v2 {label} exceeds its byte limit"
        )
    copied = json.loads(encoded)
    if type(copied) is not dict:
        raise BodySwayDynamicSeamSourceV2Error(
            f"Dynamic seam source v2 {label} must be an exact JSON object"
        )
    return copied


def _require_source_budget(source: dict[str, Any]) -> None:
    require_bounded_json_tree(
        source, max_nodes=MAX_SOURCE_JSON_NODES,
        max_depth=MAX_SOURCE_JSON_DEPTH,
    )
    if len(canonical_json_bytes(source)) > MAX_SOURCE_BYTES:
        raise BodySwayDynamicSeamSourceV2Error(
            "Dynamic seam source v2 exceeds its total byte limit"
        )


__all__ = [
    "BodySwayDynamicSeamSourceV2Error",
    "build_body_sway_dynamic_seam_source_v2",
]
