"""Bounded schedule and structural-check validation for P10.2."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .body_sway_probe_profile import MAX_SAMPLE_COUNT
from .idle_behavior_decision_validation_fields import (
    array_value,
    digest_value,
    exact_fields,
    object_value,
)


CHECK_ORDER = (
    "loop_closure",
    "fk_finite",
    "sampled_mesh_deformation",
    "sampled_canvas_containment",
    "shared_index_internal_continuity",
    "inter_attachment_seams",
    "visual_quality",
)
_CHECK_FIELDS = {
    "check_id", "status", "reason_code", "subject_count", "sample_count",
    "failure_count", "evidence_sha256",
}
_STRUCTURAL = frozenset(CHECK_ORDER[:5])


class BodySwayProbeEvidenceError(ValueError):
    """Raised when bounded P10.2 evidence is inconsistent or misleading."""


def require_schedule(value: Any, *, duration: int) -> int:
    """Validate the sealed full schedule identity without storing all ticks."""

    row = object_value(value, "Body-sway probe schedule")
    exact_fields(
        row, {"tick_schedule_sha256", "sample_count", "first_tick", "last_tick"},
        "Body-sway probe schedule",
    )
    digest_value(row.get("tick_schedule_sha256"), "tick_schedule_sha256")
    count = _integer(row.get("sample_count"), 2, MAX_SAMPLE_COUNT, "sample count")
    if type(row.get("first_tick")) is not int or row["first_tick"] != 0 \
            or type(row.get("last_tick")) is not int \
            or row["last_tick"] != duration:
        raise BodySwayProbeEvidenceError(
            "Body-sway schedule must span tick zero through clip duration"
        )
    return count


def require_checks(
    value: Any, *, loop: bool, schedule_count: int,
    rig_bone_count: int, attachment_count: int, mesh_attachment_count: int,
) -> dict[str, int | bool]:
    """Validate seven ordered checks and their observable/not-applicable bounds."""

    rows = array_value(value, "Body-sway checks", maximum=len(CHECK_ORDER))
    if len(rows) != len(CHECK_ORDER):
        raise BodySwayProbeEvidenceError(
            "Body-sway checks must contain the seven pinned rows"
        )
    counts = {name: 0 for name in (
        "passed", "rejected", "unobservable", "not_applicable",
    )}
    for check_id, raw in zip(CHECK_ORDER, rows, strict=True):
        row = object_value(raw, "Body-sway check")
        exact_fields(row, _CHECK_FIELDS, "Body-sway check")
        if row.get("check_id") != check_id:
            raise BodySwayProbeEvidenceError(
                "Body-sway checks are not in canonical order"
            )
        _check_row(
            row, check_id=check_id, loop=loop, schedule_count=schedule_count,
            rig_bone_count=rig_bone_count, attachment_count=attachment_count,
            mesh_count=mesh_attachment_count,
        )
        counts[row["status"]] += 1
    counts["structural_rejected"] = any(
        row["status"] == "rejected" and row["check_id"] in _STRUCTURAL
        for row in rows
    )
    return counts


def _check_row(
    row: Mapping[str, Any], *, check_id: str, loop: bool,
    schedule_count: int, rig_bone_count: int,
    attachment_count: int, mesh_count: int,
) -> None:
    if any(type(row.get(field)) is not int for field in (
        "subject_count", "sample_count", "failure_count",
    )):
        raise BodySwayProbeEvidenceError(
            f"Body-sway {check_id} evidence counts must be integers"
        )
    if check_id == "inter_attachment_seams":
        return _fixed_unobservable(row, "reviewed_seam_anchors_missing")
    if check_id == "visual_quality":
        return _fixed_unobservable(row, "manual_runtime_preview_required")
    if check_id == "loop_closure" and not loop:
        return _fixed_not_applicable(row, "clip_not_looping")
    expected = {
        "loop_closure": (1, 2),
        "fk_finite": (rig_bone_count, schedule_count),
        "sampled_mesh_deformation": (mesh_count, schedule_count),
        "sampled_canvas_containment": (attachment_count, schedule_count),
        "shared_index_internal_continuity": (mesh_count, schedule_count),
    }[check_id]
    if expected[0] == 0:
        return _fixed_not_applicable(row, "reviewed_noop")
    if row.get("subject_count") != expected[0] \
            or row.get("sample_count") != expected[1]:
        raise BodySwayProbeEvidenceError(
            f"Body-sway {check_id} evidence counts differ from its inventory"
        )
    _computed_status(row)


def _computed_status(row: Mapping[str, Any]) -> None:
    status, failures = row.get("status"), row.get("failure_count")
    if status not in {"passed", "rejected"} \
            or type(failures) is not int \
            or not 0 <= failures <= row["sample_count"] \
            or status == "passed" and failures != 0 \
            or status == "rejected" and failures == 0 \
            or row.get("reason_code") != f"sampled_check_{status}":
        raise BodySwayProbeEvidenceError(
            "Body-sway computed check status is inconsistent"
        )
    digest_value(row.get("evidence_sha256"), "check evidence_sha256")


def _fixed_unobservable(row: Mapping[str, Any], reason: str) -> None:
    if row != {
        "check_id": row["check_id"], "status": "unobservable",
        "reason_code": reason, "subject_count": 0, "sample_count": 0,
        "failure_count": 0, "evidence_sha256": None,
    }:
        raise BodySwayProbeEvidenceError(
            f"Body-sway {row['check_id']} must remain unobservable"
        )


def _fixed_not_applicable(row: Mapping[str, Any], reason: str) -> None:
    if row != {
        "check_id": row["check_id"], "status": "not_applicable",
        "reason_code": reason, "subject_count": 0, "sample_count": 0,
        "failure_count": 0, "evidence_sha256": None,
    }:
        raise BodySwayProbeEvidenceError(
            f"Body-sway {row['check_id']} not-applicable row is inconsistent"
        )


def _integer(value: Any, minimum: int, maximum: int, label: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise BodySwayProbeEvidenceError(f"Body-sway {label} is invalid")
    return value
