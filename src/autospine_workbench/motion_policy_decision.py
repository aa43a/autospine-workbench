"""Build one explicitly human-reviewed MotionPolicyDecision v1 document."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .motion_policy_candidate_inventory import (
    MotionPolicyCandidateInventoryError,
    derive_motion_policy_candidates,
)
from .motion_policy_decision_validation import (
    FORMAT,
    FORMAT_VERSION,
    MotionPolicyDecisionValidationError,
    require_motion_policy_decision,
)


class MotionPolicyDecisionError(ValueError):
    """Raised when explicit review input cannot form a decision contract."""


@dataclass(frozen=True, slots=True)
class MotionPolicyDecision:
    """Frozen canonical reviewed decision with isolated document access."""

    _canonical_json: str

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_json(self) -> str:
        return self._canonical_json

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


def build_motion_policy_decision(
    foot_candidates: Mapping[str, Any],
    depth_candidates: Mapping[str, Any],
    *,
    review: Mapping[str, Any],
    decisions: list[Mapping[str, Any]],
    root_release_keys: list[Mapping[str, Any]],
    draw_order_loop_reset: Mapping[str, Any],
) -> MotionPolicyDecision:
    """Bind explicit human decisions; never infer choices or release keys."""

    try:
        inventory = derive_motion_policy_candidates(
            foot_candidates, depth_candidates
        )
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "project_id": inventory.project_id,
            "clip_id": inventory.clip_id,
            "source": inventory.source,
            "review": _snapshot(review),
            "decisions": _snapshot(decisions),
            "root_release_keys": _snapshot(root_release_keys),
            "draw_order_loop_reset": _snapshot(draw_order_loop_reset),
        }
        require_motion_policy_decision(
            document,
            foot_candidates=foot_candidates,
            depth_candidates=depth_candidates,
        )
        return MotionPolicyDecision(_canonical(document))
    except MotionPolicyDecisionError:
        raise
    except (
        MotionPolicyCandidateInventoryError,
        MotionPolicyDecisionValidationError,
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
    ) as exc:
        raise MotionPolicyDecisionError(
            f"Motion-policy decision build failed: {exc}"
        ) from exc


def _snapshot(value: Any) -> Any:
    return json.loads(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
