"""Pure exact-source closure for P10.5d dynamic seam analysis."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .body_sway_continuous_proof_validation import (
    BodySwayContinuousProofValidationError,
    body_sway_continuous_proof_sha256,
)
from .body_sway_dynamic_seam_profile import (
    MAX_CONTINUOUS_PROOF_BYTES,
    MAX_REVIEWED_SET_BYTES,
    MAX_SEAM_CANDIDATE_BYTES,
    MAX_SEAM_DECISION_BYTES,
    MAX_SOURCE_BYTES,
    MAX_SOURCE_JSON_DEPTH,
    MAX_SOURCE_JSON_NODES,
    SOURCE_FIELDS,
    body_sway_dynamic_seam_source_sha256,
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


class BodySwayDynamicSeamSourceError(ValueError):
    """Raised when proof and reviewed anchors do not form one exact source."""


def build_body_sway_dynamic_seam_source(
    *,
    continuous_proof: Mapping[str, Any],
    seam_anchor_candidates: Mapping[str, Any],
    seam_anchor_review_decision: Mapping[str, Any],
    reviewed_seam_anchor_set: Mapping[str, Any],
    reviewed_set_bundle_sha256: str,
) -> dict[str, Any]:
    """Recompute every embedded artifact and seal a path-free source set."""

    try:
        proof = _copy_object(
            continuous_proof, "continuous proof",
            MAX_CONTINUOUS_PROOF_BYTES,
        )
        candidates = _copy_object(
            seam_anchor_candidates, "seam-anchor candidates",
            MAX_SEAM_CANDIDATE_BYTES,
        )
        decision = _copy_object(
            seam_anchor_review_decision, "seam-anchor review decision",
            MAX_SEAM_DECISION_BYTES,
        )
        reviewed_set = _copy_object(
            reviewed_seam_anchor_set, "reviewed seam-anchor set",
            MAX_REVIEWED_SET_BYTES,
        )
        require_sha256(
            reviewed_set_bundle_sha256,
            "Reviewed seam-anchor set bundle digest",
        )
        proof_sha = body_sway_continuous_proof_sha256(proof)
        rig = _proof_rig(proof)
        contract = build_reviewed_seam_anchor_set_bundle_contract(
            candidates, decision, rig, reviewed_set
        )
        if contract.bundle_sha256 != reviewed_set_bundle_sha256:
            raise BodySwayDynamicSeamSourceError(
                "Reviewed seam-anchor bundle digest differs from exact replay"
            )
        _require_cross_chain(proof, candidates, decision, reviewed_set,
                             contract)
        source = {
            "body_sway_continuous_proof_sha256": proof_sha,
            "body_sway_continuous_preview_proof": proof,
            "seam_anchor_candidate_sha256": contract.candidate_sha256,
            "seam_anchor_candidates": candidates,
            "seam_anchor_review_decision_sha256": contract.decision_sha256,
            "seam_anchor_review_decision": decision,
            "review_revision": contract.review_revision,
            "reviewed_seam_anchor_set_sha256": contract.set_sha256,
            "reviewed_seam_anchor_set_bundle_sha256": contract.bundle_sha256,
            "reviewed_seam_anchor_set": reviewed_set,
        }
        source["source_set_sha256"] = (
            body_sway_dynamic_seam_source_sha256(source)
        )
        _require_source_budget(source)
        return source
    except BodySwayDynamicSeamSourceError:
        raise
    except (
        AttributeError,
        BodySwayContinuousProofValidationError,
        KeyError,
        LayerManifestError,
        OverflowError,
        RecursionError,
        ReviewedSeamAnchorSetBundleContractError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as exc:
        raise BodySwayDynamicSeamSourceError(
            f"Dynamic seam source admission failed: {exc}"
        ) from exc


def require_body_sway_dynamic_seam_source(
    source: Mapping[str, Any],
) -> dict[str, Any]:
    """Rebuild a detached closure and require exact canonical identity."""

    try:
        raw = _copy_object(source, "dynamic seam source", MAX_SOURCE_BYTES)
        if set(raw) != SOURCE_FIELDS:
            raise BodySwayDynamicSeamSourceError(
                "Dynamic seam source fields are unsupported"
            )
        rebuilt = build_body_sway_dynamic_seam_source(
            continuous_proof=raw["body_sway_continuous_preview_proof"],
            seam_anchor_candidates=raw["seam_anchor_candidates"],
            seam_anchor_review_decision=raw["seam_anchor_review_decision"],
            reviewed_seam_anchor_set=raw["reviewed_seam_anchor_set"],
            reviewed_set_bundle_sha256=(
                raw["reviewed_seam_anchor_set_bundle_sha256"]
            ),
        )
        if canonical_json_bytes(raw) != canonical_json_bytes(rebuilt):
            raise BodySwayDynamicSeamSourceError(
                "Dynamic seam source identities differ from exact replay"
            )
        return rebuilt
    except BodySwayDynamicSeamSourceError:
        raise
    except (
        AttributeError, KeyError, OverflowError, RecursionError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayDynamicSeamSourceError(
            f"Dynamic seam source validation failed: {exc}"
        ) from exc


def _proof_rig(proof: dict[str, Any]) -> dict[str, Any]:
    source = proof["source"]
    rig = source["rig_ir"]
    if type(rig) is not dict or canonical_sha256(rig) \
            != source["rig_ir_sha256"]:
        raise BodySwayDynamicSeamSourceError(
            "Dynamic seam proof RigIR identity is inconsistent"
        )
    return rig


def _require_cross_chain(proof, candidates, decision, reviewed_set,
                         contract) -> None:
    project_id = proof["project_id"]
    p3 = proof["source"]["amplitude_envelope_candidate"]["source"] \
        ["reviewed_probe_report"]["source"]["p3"]
    candidate_source = candidates["source"]
    reviewed_source = reviewed_set["source"]
    if any(document.get("project_id") != project_id for document in (
        candidates, decision, reviewed_set,
    )) or contract.project_id != project_id:
        raise BodySwayDynamicSeamSourceError(
            "Dynamic seam project identities are cross-wired"
        )
    p3_expected = {
        "layer_manifest_sha256": p3["layer_manifest_sha256"],
        "rig_sha256": p3["rig_sha256"],
        "bundle_sha256": p3["bundle_sha256"],
    }
    if any(candidate_source[field] != value
           for field, value in p3_expected.items()) \
            or proof["source"]["rig_ir_sha256"] != p3_expected["rig_sha256"]:
        raise BodySwayDynamicSeamSourceError(
            "Dynamic seam manifest or exact P3 identity is cross-wired"
        )
    expected_reviewed_source = {
        "layer_manifest_sha256": p3_expected["layer_manifest_sha256"],
        "p3_rig_sha256": p3_expected["rig_sha256"],
        "p3_bundle_sha256": p3_expected["bundle_sha256"],
        "seam_anchor_candidate_sha256": contract.candidate_sha256,
        "review_revision": contract.review_revision,
        "seam_anchor_review_decision_sha256": contract.decision_sha256,
    }
    if reviewed_source != expected_reviewed_source \
            or contract.set_sha256 != canonical_sha256(reviewed_set):
        raise BodySwayDynamicSeamSourceError(
            "Dynamic seam reviewed-set provenance is cross-wired"
        )


def _copy_object(value: Any, label: str, byte_limit: int) -> dict[str, Any]:
    require_bounded_json_tree(
        value, max_nodes=MAX_SOURCE_JSON_NODES,
        max_depth=MAX_SOURCE_JSON_DEPTH,
    )
    encoded = canonical_json_bytes(value)
    if len(encoded) > byte_limit:
        raise BodySwayDynamicSeamSourceError(
            f"Dynamic seam {label} exceeds its byte limit"
        )
    copied = json.loads(encoded)
    if type(copied) is not dict:
        raise BodySwayDynamicSeamSourceError(
            f"Dynamic seam {label} must be an exact JSON object"
        )
    return copied


def _require_source_budget(source: dict[str, Any]) -> None:
    require_bounded_json_tree(
        source, max_nodes=MAX_SOURCE_JSON_NODES,
        max_depth=MAX_SOURCE_JSON_DEPTH,
    )
    if len(canonical_json_bytes(source)) > MAX_SOURCE_BYTES:
        raise BodySwayDynamicSeamSourceError(
            "Dynamic seam source exceeds its total byte limit"
        )
