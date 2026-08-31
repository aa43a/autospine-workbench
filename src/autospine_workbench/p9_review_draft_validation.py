"""Semantic validation for an immutable pending P9 review draft."""

from __future__ import annotations

from collections.abc import Mapping
import json
import re
from typing import Any

from .depth_pair_policy import FORMAT as POLICY_FORMAT, require_depth_pair_policy
from .foot_lock_candidate_validation import require_foot_lock_candidates


_DRAFT_FORMAT = "autospine-motion-policy-review-draft"
_PROPOSAL_FORMAT = "autospine-depth-pair-policy-proposal"
_SHA = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_FIELDS = {
    "p3": {"rig_sha256", "bundle_sha256"},
    "p4": {"profile_sha256", "bundle_sha256"},
    "p5": {"instance_sha256", "bundle_sha256"},
    "p7": {"motion_sha256", "bundle_sha256"},
    "p8": {"motion_sha256", "bundle_sha256"},
}


class P9ReviewDraftValidationError(ValueError):
    """Raised when pending draft semantics or exact sources differ."""


def require_p9_review_draft_contract(
    manifest: Mapping[str, Any],
    proposal: Mapping[str, Any],
    foot: Mapping[str, Any],
    project: str,
    namespace: str,
) -> None:
    _require_manifest(manifest, project, namespace)
    _require_proposal(proposal)
    require_foot_lock_candidates(foot)
    approved_policy_from_proposal(proposal)
    _require_cross_source(manifest, proposal, foot)


def approved_policy_from_proposal(
    proposal: Mapping[str, Any],
) -> dict[str, Any]:
    """Compile the only policy the explicit proposal confirmation can approve."""

    _require_proposal(proposal)
    value = json.loads(json.dumps(proposal, allow_nan=False))
    if value.pop("proposal", None) is None:
        raise P9ReviewDraftValidationError("Depth proposal metadata is absent")
    value["format"] = POLICY_FORMAT
    value["review"] = {"status": "approved", "method": "human"}
    require_depth_pair_policy(value)
    return value


def _require_manifest(value, project: str, namespace: str) -> None:
    if set(value) != {
        "format", "format_version", "status", "authority", "project_id",
        "motion_namespace", "clip_id", "source", "outputs",
    } or value.get("format") != _DRAFT_FORMAT or value.get("format_version") != 1 \
            or value.get("status") != "pending_human_depth_policy_review" \
            or value.get("project_id") != project \
            or value.get("motion_namespace") != namespace:
        raise P9ReviewDraftValidationError(
            "P9 draft manifest contract differs"
        )
    if value.get("authority") != {
        "approved_depth_policy": False,
        "depth_candidates_emitted": False,
        "p9_adoption_emitted": False,
    }:
        raise P9ReviewDraftValidationError("P9 draft authority is not pending")
    source = value.get("source")
    outputs = value.get("outputs")
    if not isinstance(source, Mapping) or set(source) != set(_SOURCE_FIELDS):
        raise P9ReviewDraftValidationError("P9 draft source stages differ")
    for stage, fields in _SOURCE_FIELDS.items():
        row = source.get(stage)
        if not isinstance(row, Mapping) or set(row) != fields \
                or any(not isinstance(item, str) or not _SHA.fullmatch(item)
                       for item in row.values()):
            raise P9ReviewDraftValidationError(
                f"P9 draft {stage} source differs"
            )
    expected_outputs = {
        "kimodo_policy_evidence_sha256", "foot_candidates_sha256",
        "depth_pair_policy_proposal_sha256",
    }
    if not isinstance(outputs, Mapping) or set(outputs) != expected_outputs \
            or any(not isinstance(item, str) or not _SHA.fullmatch(item)
                   for item in outputs.values()):
        raise P9ReviewDraftValidationError("P9 draft outputs differ")


def _require_proposal(value) -> None:
    if value.get("format") != _PROPOSAL_FORMAT \
            or value.get("format_version") != 1 \
            or value.get("review") != {
                "status": "pending_human_review", "method": "human",
            } or set(value) != {
                "format", "format_version", "policy_id", "project_id",
                "clip_id", "source", "review", "hysteresis", "pairs",
                "proposal",
            }:
        raise P9ReviewDraftValidationError("Depth proposal contract differs")
    metadata = value.get("proposal")
    if not isinstance(metadata, Mapping) or set(metadata) != {
        "method", "scope", "rationale", "limitations",
    } or metadata.get("method") != "exact-single-pair-operator-review-v1":
        raise P9ReviewDraftValidationError("Depth proposal metadata differs")
    if not isinstance(value.get("pairs"), list) or len(value["pairs"]) != 1:
        raise P9ReviewDraftValidationError(
            "Single-pair operator review requires exactly one Depth pair"
        )


def _require_cross_source(manifest, proposal, foot) -> None:
    source = manifest["source"]
    policy_source = proposal["source"]
    foot_source = foot["source"]
    if proposal["project_id"] != manifest["project_id"] \
            or proposal["clip_id"] != manifest["clip_id"] \
            or foot["project_id"] != manifest["project_id"] \
            or foot["clip_id"] != manifest["clip_id"]:
        raise P9ReviewDraftValidationError(
            "P9 draft project or clip is cross-wired"
        )
    checks = (
        (source["p3"]["rig_sha256"], policy_source["p3"]["rig_sha256"]),
        (source["p3"]["bundle_sha256"], policy_source["p3"]["bundle_sha256"]),
        (source["p5"]["instance_sha256"], foot_source["motion_instance_sha256"]),
        (source["p5"]["bundle_sha256"], foot_source["retarget_bundle_sha256"]),
        (source["p8"]["motion_sha256"], foot_source["projected_motion_sha256"]),
        (source["p8"]["bundle_sha256"], foot_source["projected_bundle_sha256"]),
    )
    if any(left != right for left, right in checks):
        raise P9ReviewDraftValidationError(
            "P9 draft exact sources are cross-wired"
        )


__all__ = [
    "P9ReviewDraftValidationError", "approved_policy_from_proposal",
    "require_p9_review_draft_contract",
]
