"""Strict standalone BodySwayProbeReport v1 structural evidence contract."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .body_sway_probe_evidence_validation import (
    BodySwayProbeEvidenceError,
    CHECK_ORDER,
    require_checks,
    require_schedule,
)
from .body_sway_probe_profile import body_sway_probe_profile
from .body_sway_probe_sample_validation import (
    BodySwayProbeSampleError,
    SAMPLE_HASH_DOMAIN,
    require_sample_stream,
)
from .idle_behavior_candidate_validation import BODY_SWAY_PROPOSAL
from .idle_behavior_decision_validation_fields import (
    IdleBehaviorDecisionFieldError,
    digest_value,
    exact_fields,
    identifier_value,
    object_value,
    require_decisions,
    require_timing,
)
from .resolved_project import canonical_sha256


FORMAT = "autospine-body-sway-probe-report"
FORMAT_VERSION = 1
MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
_TOP = {
    "format", "format_version", "project_id", "clip_id", "source",
    "timing", "selection", "prober", "semantics", "schedule",
    "sample_stream", "checks", "status", "release_gate", "summary",
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
SEMANTICS = {
    "scope": "sampled-structural",
    "mode": "diagnostic-only",
    "motion_instance_v3_emitted": False,
    "runtime_timeline_emitted": False,
    "safe_range_claimed": False,
    "review_input_envelope_max_deg": 10.0,
    "review_input_envelope_is_safety_evidence": False,
    "continuous_time_safety_claimed": False,
    "visual_quality_claimed": False,
    "raster_truth_claimed": False,
    "inter_attachment_seam_safety_claimed": False,
    "manual_runtime_preview_required": True,
    "bulk_evidence_digests_are_compiler_seals": True,
    "bulk_evidence_standalone_replay_claimed": False,
    "representative_sample_digest_domain": SAMPLE_HASH_DOMAIN,
}
_SUMMARY = {
    "schedule_sample_count", "representative_sample_count",
    "rig_bone_count", "rotation_bone_count", "overlay_bone_count",
    "attachment_count", "mesh_attachment_count", "check_count",
    "passed_check_count", "rejected_check_count", "unobservable_check_count",
    "not_applicable_check_count",
}
_INVENTORY_SUMMARY = {
    "representative_sample_count", "rig_bone_count", "rotation_bone_count",
    "overlay_bone_count", "attachment_count", "mesh_attachment_count",
}


class BodySwayProbeValidationError(ValueError):
    """Raised when a probe report overclaims or carries inconsistent evidence."""


def require_body_sway_probe_report(document: Mapping[str, Any]) -> None:
    """Validate standalone shape, internal derivations, and blocked release gate."""

    try:
        root = object_value(document, "Body-sway probe report")
        exact_fields(root, _TOP, "Body-sway probe report")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root.get("format_version") != FORMAT_VERSION:
            raise BodySwayProbeValidationError(
                "Body-sway probe report format is unsupported"
            )
        identifier_value(root.get("project_id"), "project_id")
        identifier_value(root.get("clip_id"), "clip_id")
        _source(root.get("source"))
        require_timing(root.get("timing"))
        overlay_bone_ids, amplitudes = _selection(root.get("selection"))
        _fixed(root.get("prober"), body_sway_probe_profile(), "prober")
        _fixed(root.get("semantics"), SEMANTICS, "semantics")
        timing = root["timing"]
        schedule_count = require_schedule(
            root.get("schedule"), duration=timing["duration_ticks"],
        )
        inventory = require_sample_stream(
            root.get("sample_stream"), duration=timing["duration_ticks"],
            loop=timing["loop"], overlay_bone_ids=overlay_bone_ids,
            amplitudes=amplitudes, schedule_count=schedule_count,
        )
        checks = require_checks(
            root.get("checks"), loop=timing["loop"],
            schedule_count=schedule_count,
            rig_bone_count=inventory["rig_bone_count"],
            attachment_count=inventory["attachment_count"],
            mesh_attachment_count=inventory["mesh_attachment_count"],
            loop_pose_closed=inventory["loop_pose_closed"],
        )
        _aggregate(root, schedule_count, inventory, checks)
        encoded = json.dumps(
            dict(root), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise BodySwayProbeValidationError(
                "Body-sway probe report byte limit exceeded"
            )
    except BodySwayProbeValidationError:
        raise
    except (
        BodySwayProbeEvidenceError, BodySwayProbeSampleError,
        IdleBehaviorDecisionFieldError,
        KeyError, OverflowError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayProbeValidationError(
            f"Body-sway probe report validation failed: {exc}"
        ) from exc


def body_sway_probe_report_sha256(document: Mapping[str, Any]) -> str:
    """Return a canonical digest only after strict standalone validation."""

    require_body_sway_probe_report(document)
    return canonical_sha256(document)


def _source(value: Any) -> None:
    source = object_value(value, "Body-sway probe source")
    exact_fields(
        source,
        {
            "idle_behavior_candidates_sha256", "idle_behavior_decision_sha256",
            "layer_manifest_sha256", "p3", "p5", "p9",
        },
        "Body-sway probe source",
    )
    for field in (
        "idle_behavior_candidates_sha256", "idle_behavior_decision_sha256",
        "layer_manifest_sha256",
    ):
        digest_value(source.get(field), field)
    for stage, fields in (("p3", _P3), ("p5", _P5), ("p9", _P9)):
        row = object_value(source.get(stage), f"Body-sway probe {stage} source")
        exact_fields(row, fields, f"Body-sway probe {stage} source")
        for field in fields:
            digest_value(row.get(field), f"{stage}.{field}")
    if source["layer_manifest_sha256"] != source["p3"]["layer_manifest_sha256"]:
        raise BodySwayProbeValidationError(
            "Body-sway probe Layer Manifest identities disagree"
        )


def _selection(value: Any) -> tuple[list[str], dict[str, float]]:
    selection = object_value(value, "Body-sway probe selection")
    exact_fields(
        selection,
        {"candidate_id", "feature_id", "action", "probe_status", "parameters"},
        "Body-sway probe selection",
    )
    parameters = object_value(
        selection.get("parameters"), "Body-sway probe parameters",
    )
    require_decisions([{
        "candidate_id": selection.get("candidate_id"),
        "feature_id": selection.get("feature_id"),
        "action": selection.get("action"),
        "reason_code": "probe-selection",
        "payload": parameters,
        "probe_status": selection.get("probe_status"),
    }])
    bone_ids = list(BODY_SWAY_PROPOSAL["target_bone_ids"])
    amplitudes = parameters["per_bone_amplitude_deg"]
    phases = parameters["per_bone_phase_fraction"]
    if [row["bone_id"] for row in amplitudes] != bone_ids \
            or [row["bone_id"] for row in phases] != bone_ids:
        raise BodySwayProbeValidationError(
            "Body-sway probe selection differs from the candidate bone order"
        )
    return bone_ids, {
        row["bone_id"]: float(row["value"]) for row in amplitudes
    }


def _aggregate(root, schedule_count, inventory, checks) -> None:
    rejected = bool(checks["structural_rejected"])
    expected_status = "structural_rejected" if rejected \
        else "manual_visual_required"
    if root.get("status") != expected_status:
        raise BodySwayProbeValidationError(
            "Body-sway top-level status differs from structural checks"
        )
    reasons = [
        "manual_runtime_preview_required",
        "reviewed_seam_anchors_missing",
        "safe_range_unproven",
    ]
    if rejected:
        reasons.append("sampled_structural_check_rejected")
    expected_gate = {"status": "blocked", "reason_codes": sorted(reasons)}
    if root.get("release_gate") != expected_gate:
        raise BodySwayProbeValidationError(
            "Body-sway release gate must remain blocked"
        )
    expected_summary = {
        "schedule_sample_count": schedule_count,
        **{field: inventory[field] for field in _INVENTORY_SUMMARY},
        "check_count": len(CHECK_ORDER),
        "passed_check_count": checks["passed"],
        "rejected_check_count": checks["rejected"],
        "unobservable_check_count": checks["unobservable"],
        "not_applicable_check_count": checks["not_applicable"],
    }
    summary = object_value(root.get("summary"), "Body-sway probe summary")
    exact_fields(summary, _SUMMARY, "Body-sway probe summary")
    if any(type(summary.get(field)) is not int for field in _SUMMARY) \
            or summary != expected_summary:
        raise BodySwayProbeValidationError(
            "Body-sway summary differs from its bounded evidence"
        )


def _fixed(value: Any, expected: Mapping[str, Any], label: str) -> None:
    row = object_value(value, f"Body-sway probe {label}")
    try:
        matches = canonical_sha256(row) == canonical_sha256(expected)
    except (TypeError, ValueError) as exc:
        raise BodySwayProbeValidationError(
            f"Body-sway probe {label} is not canonical JSON"
        ) from exc
    if not matches:
        raise BodySwayProbeValidationError(
            f"Body-sway probe {label} is unsupported"
        )
