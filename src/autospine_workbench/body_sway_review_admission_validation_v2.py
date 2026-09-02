"""Strict standalone validation for BodySwayReviewAdmission v2."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .body_sway_probe_validation import (
    BodySwayProbeValidationError, require_body_sway_selection,
    require_body_sway_source,
)
from .body_sway_review_admission_profile_v2 import (
    MAX_ADMISSION_DOCUMENT_BYTES, admission_claims_v2,
    admission_release_gate_v2, body_sway_review_head_observation_v2,
    compiler_profile_v2,
)
from .body_sway_visual_review_candidate_validation_v2 import (
    BodySwayVisualReviewCandidateV2ValidationError,
    require_body_sway_visual_review_source_v2,
)
from .idle_behavior_decision_validation_fields import (
    IdleBehaviorDecisionFieldError, require_timing,
)
from .manifest_artifacts import (
    LayerManifestError, require_safe_token, require_sha256,
)
from .resolved_project import canonical_sha256


FORMAT = "autospine-body-sway-review-admission"
FORMAT_VERSION = 2
_TOP = {
    "format", "format_version", "project_id", "clip_id", "source",
    "timing", "selection", "head_observation", "compiler", "claims",
    "status", "release_gate",
}
_SOURCE = {
    "job", "execution", "preview_source", "evidence", "visual_review",
}
_JOB = {
    "job_id", "package_id", "terminal_event_sha256", "terminal_sequence",
}
_EXECUTION = {
    "project_id", "temporary_preview_v2_sha256",
    "runtime_execution_sha256", "runtime_execution_bundle_sha256",
    "capture_artifact_set_sha256",
}
_VISUAL = {
    "candidate_v2_sha256", "revision", "decision_v2_sha256",
    "head_decision_v2_sha256",
}
_BODY_SOURCE = {
    "idle_behavior_candidates_sha256", "idle_behavior_decision_sha256",
    "layer_manifest_sha256", "p3", "p5", "p9",
}
_PREVIEW_SOURCE = _BODY_SOURCE | {
    "body_sway_probe_report_sha256",
    "capture_framing_candidate_sha256",
    "capture_framing_decision_sha256", "capture_framing_revision",
    "current_p10_1_head",
}


class BodySwayReviewAdmissionV2ValidationError(ValueError):
    """Raised when a v2 admission is malformed, path-bearing, or stale-shaped."""


def require_body_sway_review_admission_v2(
    document: Mapping[str, Any],
) -> None:
    try:
        root = _object(document, "review admission")
        _exact(root, _TOP, "review admission")
        if root.get("format") != FORMAT \
                or root.get("format_version") != FORMAT_VERSION:
            raise BodySwayReviewAdmissionV2ValidationError(
                "Body-sway review admission v2 format is unsupported"
            )
        project = require_safe_token(root.get("project_id"), "Project id")
        require_safe_token(root.get("clip_id"), "Clip id")
        source = _source(root.get("source"), project)
        require_timing(root.get("timing"))
        require_body_sway_selection(root.get("selection"))
        visual = source["visual_review"]
        _fixed(
            root.get("head_observation"),
            body_sway_review_head_observation_v2(
                visual["revision"], visual["head_decision_v2_sha256"],
            ),
            "head observation",
        )
        _fixed(root.get("compiler"), compiler_profile_v2(), "compiler")
        _fixed(root.get("claims"), admission_claims_v2(), "claims")
        if root.get("status") != "admitted_for_safety_analysis":
            raise BodySwayReviewAdmissionV2ValidationError(
                "Body-sway review admission v2 status is unsupported"
            )
        _fixed(
            root.get("release_gate"), admission_release_gate_v2(),
            "release gate",
        )
        if _contains_path_key(root):
            raise BodySwayReviewAdmissionV2ValidationError(
                "Body-sway review admission v2 must remain path-free"
            )
        if len(_canonical(root)) > MAX_ADMISSION_DOCUMENT_BYTES:
            raise BodySwayReviewAdmissionV2ValidationError(
                "Body-sway review admission v2 exceeds its byte limit"
            )
    except BodySwayReviewAdmissionV2ValidationError:
        raise
    except _FAILURES as exc:
        raise BodySwayReviewAdmissionV2ValidationError(
            f"Body-sway review admission v2 validation failed: {exc}"
        ) from exc


def body_sway_review_admission_sha256_v2(
    document: Mapping[str, Any],
) -> str:
    require_body_sway_review_admission_v2(document)
    return canonical_sha256(document)


def _source(value: Any, project_id: str) -> Mapping[str, Any]:
    source = _object(value, "source")
    _exact(source, _SOURCE, "source")
    job = _object(source.get("job"), "job")
    _exact(job, _JOB, "job")
    require_sha256(job.get("job_id"), "Runtime capture job")
    require_sha256(
        job.get("terminal_event_sha256"), "Runtime capture terminal event",
    )
    sequence = job.get("terminal_sequence")
    if type(sequence) is not int or sequence < 1:
        raise BodySwayReviewAdmissionV2ValidationError(
            "Runtime capture terminal sequence is invalid"
        )
    require_sha256(job.get("package_id"), "Runtime capture package")
    execution = _object(source.get("execution"), "execution")
    _exact(execution, _EXECUTION, "execution")
    if execution.get("project_id") != project_id:
        raise BodySwayReviewAdmissionV2ValidationError(
            "Admission execution project differs from the document"
        )
    for field in _EXECUTION - {"project_id"}:
        require_sha256(execution.get(field), f"Admission execution {field}")
    preview_source = _object(source.get("preview_source"), "preview source")
    _preview_source(preview_source)
    evidence = _object(source.get("evidence"), "evidence")
    require_body_sway_visual_review_source_v2(evidence)
    expected = {
        "temporary_preview_v2_sha256":
            execution["temporary_preview_v2_sha256"],
        "runtime_execution_sha256": execution["runtime_execution_sha256"],
        "runtime_execution_bundle_sha256":
            execution["runtime_execution_bundle_sha256"],
        "capture_artifact_set_sha256":
            execution["capture_artifact_set_sha256"],
    }
    if any(evidence.get(key) != digest for key, digest in expected.items()):
        raise BodySwayReviewAdmissionV2ValidationError(
            "Admission execution address differs from its evidence"
        )
    shared = (
        "body_sway_probe_report_sha256",
        "capture_framing_candidate_sha256",
        "capture_framing_decision_sha256", "capture_framing_revision",
        "current_p10_1_head",
    )
    if any(preview_source[field] != evidence[field] for field in shared):
        raise BodySwayReviewAdmissionV2ValidationError(
            "Admission Preview v2 source differs from execution evidence"
        )
    _visual(source.get("visual_review"))
    return source


def _preview_source(value: Mapping[str, Any]) -> None:
    _exact(value, _PREVIEW_SOURCE, "preview source")
    require_body_sway_source({field: value[field] for field in _BODY_SOURCE})
    for field in (
        "body_sway_probe_report_sha256",
        "capture_framing_candidate_sha256",
        "capture_framing_decision_sha256",
    ):
        require_sha256(value.get(field), f"Admission preview {field}")
    revision = value.get("capture_framing_revision")
    head = _object(value.get("current_p10_1_head"), "P10.1 head")
    if type(revision) is not int or not 1 <= revision <= 64 \
            or set(head) != {
                "candidate_sha256", "decision_sha256", "revision",
            }:
        raise BodySwayReviewAdmissionV2ValidationError(
            "Admission Preview v2 source head is invalid"
        )
    require_sha256(head.get("candidate_sha256"), "Admission P10.1 candidate")
    require_sha256(head.get("decision_sha256"), "Admission P10.1 decision")
    if type(head.get("revision")) is not int \
            or not 1 <= head["revision"] <= 64 \
            or head["candidate_sha256"] \
                != value["idle_behavior_candidates_sha256"] \
            or head["decision_sha256"] \
                != value["idle_behavior_decision_sha256"]:
        raise BodySwayReviewAdmissionV2ValidationError(
            "Admission P10.1 head differs from Preview v2 source"
        )


def _visual(value: Any) -> None:
    row = _object(value, "visual review")
    _exact(row, _VISUAL, "visual review")
    for field in _VISUAL - {"revision"}:
        require_sha256(row.get(field), f"Admission visual review {field}")
    revision = row.get("revision")
    if type(revision) is not int or not 1 <= revision <= 64 \
            or row["decision_v2_sha256"] \
                != row["head_decision_v2_sha256"]:
        raise BodySwayReviewAdmissionV2ValidationError(
            "Admission decision must be the observed v2 review head"
        )


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BodySwayReviewAdmissionV2ValidationError(
            f"Body-sway review admission v2 {label} must be an object"
        )
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise BodySwayReviewAdmissionV2ValidationError(
            f"Body-sway review admission v2 {label} fields are unsupported"
        )


def _fixed(value: Any, expected: Any, label: str) -> None:
    if _canonical(value) != _canonical(expected):
        raise BodySwayReviewAdmissionV2ValidationError(
            f"Body-sway review admission v2 {label} is unsupported"
        )


def _contains_path_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            key == "path" or _contains_path_key(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_path_key(item) for item in value)
    return False


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


_FAILURES = (
    BodySwayProbeValidationError,
    BodySwayVisualReviewCandidateV2ValidationError,
    IdleBehaviorDecisionFieldError, KeyError, LayerManifestError,
    OverflowError, RecursionError, TypeError, UnicodeError, ValueError,
)


__all__ = [
    "FORMAT", "FORMAT_VERSION", "BodySwayReviewAdmissionV2ValidationError",
    "body_sway_review_admission_sha256_v2",
    "require_body_sway_review_admission_v2",
]
