"""Project a bound split decision into reviewed materialized child fields."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class SplitMaterializationReviewError(ValueError):
    """Raised when a decision's current claim contradicts this materialization."""


@dataclass(frozen=True, slots=True)
class SplitChildReview:
    reviewed: bool
    candidate_bone: str | None


def resolve_split_child_review(
    layer: Mapping[str, Any],
    authoring: Mapping[str, Any],
    operation_config_sha256: str,
    side: str,
) -> SplitChildReview:
    """Return reviewed state after checking every current provenance claim."""

    part = authoring.get("parts", {}).get(side, {})
    bone = part.get("candidate_bone") if isinstance(part, Mapping) else None
    decision = layer.get("split_decision")
    if not isinstance(decision, Mapping) or decision.get("binding_status") != "current":
        return SplitChildReview(False, bone if isinstance(bone, str) else None)
    analysis = decision.get("analysis")
    split_spec_sha = (
        analysis.get("split_spec_sha256") if isinstance(analysis, Mapping) else None
    )
    if (
        decision.get("operation_config_sha256") != operation_config_sha256
        or split_spec_sha != authoring.get("split_spec_sha256")
    ):
        raise SplitMaterializationReviewError(
            f"Layer {layer.get('id')} current split decision contradicts materialization"
        )
    reviewed = decision.get("action") == "accept"
    if reviewed and not isinstance(bone, str):
        raise SplitMaterializationReviewError(
            f"Layer {layer.get('id')} accepted split has no exact candidate bone"
        )
    return SplitChildReview(reviewed, bone if isinstance(bone, str) else None)
