"""Strict standalone and candidate-aware IdleBehaviorDecision v1 validation."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .idle_behavior_candidate_validation import (
    IdleBehaviorCandidateValidationError,
    idle_behavior_candidates_sha256,
    require_idle_behavior_candidates,
)
from .idle_behavior_decision_validation_fields import (
    IdleBehaviorDecisionFieldError,
    exact_fields as _exact,
    identifier_value as _identifier,
    object_value as _object,
    require_decisions as _decisions,
    require_review as _review,
    require_source as _source,
    require_timing as _timing,
)
from .resolved_project import canonical_sha256


FORMAT = "autospine-idle-behavior-decision"
FORMAT_VERSION = 1
MAX_DOCUMENT_BYTES = 64 * 1024 * 1024
_TOP = {
    "format", "format_version", "project_id", "clip_id", "source",
    "timing", "review", "semantics", "decisions", "summary",
}
SEMANTICS = {
    "mode": "decision_only",
    "review_authority": "human",
    "runtime_timeline_emitted": False,
    "safe_range_claimed": False,
    "automatic_acceptance": False,
}
_SUMMARY_FIELDS = {
    "candidate_count", "decision_count", "adjust_count", "reject_count",
    "unobservable_count", "pending_probe_count",
}


class IdleBehaviorDecisionValidationError(ValueError):
    """Raised when an idle behavior decision is unsafe or ambiguous."""


def require_idle_behavior_decision(
    document: Mapping[str, Any], *,
    candidates: Mapping[str, Any] | None = None,
) -> None:
    """Validate standalone shape and, when supplied, exact candidate binding."""

    try:
        root = _object(document, "Idle behavior decision")
        _exact(root, _TOP, "Idle behavior decision")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root.get("format_version") != FORMAT_VERSION:
            raise IdleBehaviorDecisionValidationError(
                "Idle behavior decision format is unsupported"
            )
        _identifier(root.get("project_id"), "project_id")
        _identifier(root.get("clip_id"), "clip_id")
        _source(root.get("source"))
        _timing(root.get("timing"))
        _review(root.get("review"))
        if root.get("semantics") != SEMANTICS:
            raise IdleBehaviorDecisionValidationError(
                "Idle behavior decision semantics are unsupported"
            )
        counts = _decisions(root.get("decisions"))
        _summary(root.get("summary"), counts)
        if candidates is not None:
            _candidate_binding(root, candidates)
        encoded = json.dumps(
            dict(root), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise IdleBehaviorDecisionValidationError(
                "Idle behavior decision byte limit exceeded"
            )
    except IdleBehaviorDecisionValidationError:
        raise
    except (
        IdleBehaviorCandidateValidationError,
        IdleBehaviorDecisionFieldError,
        KeyError,
        OverflowError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as exc:
        raise IdleBehaviorDecisionValidationError(
            f"Idle behavior decision validation failed: {exc}"
        ) from exc


def idle_behavior_decision_sha256(document: Mapping[str, Any]) -> str:
    """Return a canonical digest only after standalone validation."""

    require_idle_behavior_decision(document)
    return canonical_sha256(document)


def _summary(value: Any, counts: Mapping[str, int]) -> None:
    summary = _object(value, "Idle behavior decision summary")
    _exact(summary, _SUMMARY_FIELDS, "Idle behavior decision summary")
    expected = {
        "candidate_count": counts["decision"],
        "decision_count": counts["decision"],
        "adjust_count": counts["adjust"],
        "reject_count": counts["reject"],
        "unobservable_count": counts["unobservable"],
        "pending_probe_count": counts["pending_probe"],
    }
    if any(type(summary.get(field)) is not int for field in _SUMMARY_FIELDS) \
            or summary != expected:
        raise IdleBehaviorDecisionValidationError(
            "Idle behavior decision summary differs from its decisions"
        )


def _candidate_binding(
    document: Mapping[str, Any], candidates: Mapping[str, Any]
) -> None:
    require_idle_behavior_candidates(candidates)
    if document["project_id"] != candidates["project_id"] \
            or document["clip_id"] != candidates["clip_id"] \
            or document["timing"] != candidates["timing"]:
        raise IdleBehaviorDecisionValidationError(
            "Idle behavior decision project, clip, or timing binding is stale"
        )
    expected_source = source_from_candidates(candidates)
    if document["source"] != expected_source:
        raise IdleBehaviorDecisionValidationError(
            "Idle behavior decision candidate source binding is stale"
        )
    expected = sorted(
        (
            row["candidate_id"], row["feature_id"],
            row["proposal"]["target_bone_ids"],
        )
        for row in candidates["features"]
        if row["availability"] == "candidate"
    )
    decisions = document["decisions"]
    actual = [(row["candidate_id"], row["feature_id"]) for row in decisions]
    if actual != [(candidate_id, feature_id)
                  for candidate_id, feature_id, _ in expected]:
        raise IdleBehaviorDecisionValidationError(
            "Idle behavior decisions are not exhaustive for candidate rows"
        )
    for decision, (_, _, bone_ids) in zip(decisions, expected, strict=True):
        if decision["action"] == "adjust":
            payload = decision["payload"]
            amplitude_ids = [
                row["bone_id"]
                for row in payload["per_bone_amplitude_deg"]
            ]
            phase_ids = [
                row["bone_id"]
                for row in payload["per_bone_phase_fraction"]
            ]
            if amplitude_ids != bone_ids or phase_ids != bone_ids:
                raise IdleBehaviorDecisionValidationError(
                    "Body-sway parameter bone order differs from its proposal"
                )


def source_from_candidates(candidates: Mapping[str, Any]) -> dict[str, str]:
    """Derive the exact audit identities copied into a decision document."""

    require_idle_behavior_candidates(candidates)
    return {
        "idle_behavior_candidates_sha256":
            idle_behavior_candidates_sha256(candidates),
        "target_profile_sha256":
            candidates["source"]["p5"]["target_profile_sha256"],
        "motion_instance_v2_sha256":
            candidates["source"]["p9"]["motion_instance_v2_sha256"],
        "reviewed_motion_bundle_sha256":
            candidates["source"]["p9"]["bundle_sha256"],
    }
