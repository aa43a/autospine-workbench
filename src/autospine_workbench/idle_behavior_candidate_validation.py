"""Strict standalone validation for candidate-only idle behavior evidence."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .idle_behavior_candidate_identity import require_candidate_id_binding
from .idle_behavior_candidate_validation_fields import (
    array_value as _array,
    digest_value as _digest,
    exact_fields as _exact,
    identifier_value as _identifier,
    object_value as _object,
    require_evidence as _evidence,
    require_sorted_ids as _sorted_ids,
)
from .resolved_project import canonical_sha256


FORMAT = "autospine-idle-behavior-candidates"
FORMAT_VERSION = 1
MAX_DOCUMENT_BYTES = 64 * 1024 * 1024
_TOP = {
    "format", "format_version", "project_id", "clip_id", "source",
    "timing", "target_capabilities", "generator", "semantics",
    "features", "summary",
}
_P3 = {
    "base_rig_sha256", "base_bundle_sha256", "layer_manifest_sha256",
    "resolved_project_sha256", "rig_sha256", "run_sha256",
    "probes_sha256", "visuals_sha256", "bundle_sha256",
}
_P5 = {
    "target_profile_sha256", "instance_sha256", "run_sha256",
    "retarget_report_sha256", "mesh_regression_sha256", "bundle_sha256",
}
_P9 = {
    "foot_lock_candidates_sha256", "depth_order_candidates_sha256",
    "motion_policy_decision_sha256", "reviewed_motion_policy_sha256",
    "motion_instance_v2_sha256", "run_sha256", "bundle_sha256",
}
FEATURE_ORDER = ("blink", "body_sway", "hair_spring", "mouth")
TARGET_CAPABILITIES = {
    "adapter_id": "autospine-spine42-json-adapter",
    "adapter_version": "2.0.0",
    "bone_rotation": True, "root_translation": True, "draw_order": True,
    "attachment_switching": False, "deform": False, "physics": False,
    "extra_bones": False,
}
GENERATOR = {
    "id": "idle-behavior-candidate-compiler",
    "version": "1.0.0",
    "candidate_id_domain": "autospine-idle-behavior-candidate-id/v1",
}
SEMANTICS = {
    "mode": "candidate_only", "apply_policy": "review_required",
    "decision_emitted": False, "runtime_timeline_emitted": False,
    "generated_raster_emitted": False, "synthetic_visual_state_emitted": False,
    "raster_truth_claimed": False,
}
BODY_SWAY_PROPOSAL = {
    "kind": "reviewed-periodic-body-sway",
    "target_bone_ids": ["pelvis-spine", "spine-chest", "chest-neck", "neck-head"],
    "required_review_parameters": [
        "cycles", "per_bone_amplitude_deg", "per_bone_phase_fraction",
    ],
    "safe_range_evidence": "unprobed",
}


class IdleBehaviorCandidateValidationError(ValueError):
    """Raised when idle behavior candidate evidence is unsafe or ambiguous."""


def require_idle_behavior_candidates(document: Mapping[str, Any]) -> None:
    """Require the complete standalone IdleBehaviorCandidates v1 contract."""
    try:
        root = _object(document, "Idle behavior candidates")
        _exact(root, _TOP, "Idle behavior candidates")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root.get("format_version") != FORMAT_VERSION:
            raise IdleBehaviorCandidateValidationError(
                "Idle behavior candidate format is unsupported"
            )
        _identifier(root.get("project_id"), "project_id")
        _identifier(root.get("clip_id"), "clip_id")
        _source(root.get("source"))
        _timing(root.get("timing"))
        _fixed_object(
            root.get("target_capabilities"), TARGET_CAPABILITIES,
            "target capabilities",
        )
        _fixed_object(root.get("generator"), GENERATOR, "generator")
        _fixed_object(root.get("semantics"), SEMANTICS, "semantics")
        counts = _features(root.get("features"))
        require_candidate_id_binding(root)
        _summary(root.get("summary"), counts)
        encoded = json.dumps(
            dict(root), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise IdleBehaviorCandidateValidationError(
                "Idle behavior candidate byte limit exceeded"
            )
    except IdleBehaviorCandidateValidationError:
        raise
    except (KeyError, OverflowError, TypeError, UnicodeError, ValueError) as exc:
        raise IdleBehaviorCandidateValidationError(
            f"Idle behavior candidate validation failed: {exc}"
        ) from exc


def idle_behavior_candidates_sha256(document: Mapping[str, Any]) -> str:
    """Return a canonical digest only after standalone validation."""
    require_idle_behavior_candidates(document)
    return canonical_sha256(document)


def _source(value: Any) -> None:
    source = _object(value, "Idle behavior source")
    _exact(source, {"layer_manifest_sha256", "p3", "p5", "p9"},
           "Idle behavior source")
    _digest(source.get("layer_manifest_sha256"), "layer_manifest_sha256")
    for stage, fields in (("p3", _P3), ("p5", _P5), ("p9", _P9)):
        row = _object(source.get(stage), f"Idle behavior {stage} source")
        _exact(row, fields, f"Idle behavior {stage} source")
        for field in fields:
            _digest(row.get(field), f"{stage}.{field}")
    if source["layer_manifest_sha256"] != source["p3"]["layer_manifest_sha256"]:
        raise IdleBehaviorCandidateValidationError(
            "Idle behavior layer manifest identities disagree"
        )


def _timing(value: Any) -> None:
    timing = _object(value, "Idle behavior timing")
    _exact(timing, {"ticks_per_second", "duration_ticks", "loop"},
           "Idle behavior timing")
    duration = timing.get("duration_ticks")
    if timing.get("ticks_per_second") != 1_000_000 \
            or type(timing.get("ticks_per_second")) is not int \
            or type(duration) is not int or not 1 <= duration <= 600_000_000 \
            or type(timing.get("loop")) is not bool:
        raise IdleBehaviorCandidateValidationError(
            "Idle behavior timing is invalid"
        )


def _features(value: Any) -> tuple[int, int, int]:
    rows = _array(value, "Idle behavior features", maximum=4)
    if len(rows) != 4:
        raise IdleBehaviorCandidateValidationError(
            "Idle behavior features must contain all four feature rows"
        )
    counts = {"candidate": 0, "unobservable": 0, "unsupported": 0}
    for expected_id, raw in zip(FEATURE_ORDER, rows, strict=True):
        row = _object(raw, "Idle behavior feature")
        _exact(row, {
            "feature_id", "availability", "candidate_id", "evidence",
            "reason_codes", "proposal",
        }, "Idle behavior feature")
        if row.get("feature_id") != expected_id:
            raise IdleBehaviorCandidateValidationError(
                "Idle behavior features are not in canonical order"
            )
        availability = row.get("availability")
        if availability not in counts:
            raise IdleBehaviorCandidateValidationError(
                "Idle behavior feature availability is unsupported"
            )
        counts[availability] += 1
        _evidence(row.get("evidence"))
        _sorted_ids(row.get("reason_codes"), "reason codes")
        _candidate_payload(row, expected_id, availability)
    return counts["candidate"], counts["unobservable"], counts["unsupported"]


def _candidate_payload(
    row: Mapping[str, Any], feature_id: str, availability: str
) -> None:
    candidate_id, proposal = row.get("candidate_id"), row.get("proposal")
    if availability == "candidate":
        _identifier(candidate_id, "candidate_id")
        if feature_id != "body_sway" or proposal != BODY_SWAY_PROPOSAL:
            raise IdleBehaviorCandidateValidationError(
                "Only body_sway has the supported candidate proposal"
            )
    elif candidate_id is not None or proposal is not None:
        raise IdleBehaviorCandidateValidationError(
            "Unavailable idle features cannot carry candidate output"
        )


def _summary(value: Any, counts: tuple[int, int, int]) -> None:
    summary = _object(value, "Idle behavior summary")
    expected = {
        "status": "candidate_only", "feature_count": 4,
        "candidate_count": counts[0], "unobservable_count": counts[1],
        "unsupported_count": counts[2],
    }
    _exact(summary, set(expected), "Idle behavior summary")
    if any(type(summary.get(field)) is not int for field in (
        "feature_count", "candidate_count", "unobservable_count",
        "unsupported_count",
    )) or summary != expected:
        raise IdleBehaviorCandidateValidationError(
            "Idle behavior summary differs from its feature rows"
        )


def _fixed_object(value: Any, expected: dict[str, Any], label: str) -> None:
    row = _object(value, f"Idle behavior {label}")
    _exact(row, set(expected), f"Idle behavior {label}")
    boolean_fields = [
        field for field, item in expected.items() if type(item) is bool
    ]
    if any(type(row.get(field)) is not bool for field in boolean_fields) \
            or row != expected:
        raise IdleBehaviorCandidateValidationError(
            f"Idle behavior {label} is unsupported"
        )
