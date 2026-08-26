"""Strict standalone semantics for BodySwayReviewAdmission v1."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .body_sway_probe_validation import (
    BodySwayProbeValidationError,
    require_body_sway_selection,
    require_body_sway_source,
)
from .body_sway_review_admission_profile import (
    MAX_ADMISSION_DOCUMENT_BYTES,
    admission_claims,
    admission_release_gate,
    body_sway_review_head_observation,
    compiler_profile,
)
from .idle_behavior_decision_validation_fields import (
    IdleBehaviorDecisionFieldError,
    require_timing,
)
from .manifest_artifacts import (
    LayerManifestError,
    require_safe_token,
    require_sha256,
)
from .resolved_project import canonical_sha256


FORMAT = "autospine-body-sway-review-admission"
FORMAT_VERSION = 1
_TOP = {
    "format", "format_version", "project_id", "clip_id", "source",
    "timing", "selection", "head_observation", "compiler", "claims",
    "status", "release_gate",
}
_SOURCE = {"p10_chain", "capture", "visual_review"}
_CHAIN = {
    "body_sway_probe_report_sha256", "idle_behavior_candidates_sha256",
    "idle_behavior_decision_sha256", "layer_manifest_sha256", "p3", "p5",
    "p9",
}
_CAPTURE = {
    "project_id", "temporary_preview_sha256",
    "runtime_capture_manifest_sha256", "runtime_capture_bundle_sha256",
    "capture_artifact_set_sha256", "preview_artifact_set_sha256",
}
_VISUAL = {
    "candidate_sha256", "revision", "decision_sha256",
    "head_decision_sha256",
}


class BodySwayReviewAdmissionValidationError(ValueError):
    """Raised when an admission is stale, path-bearing, or overclaims."""


def require_body_sway_review_admission(
    document: Mapping[str, Any],
) -> None:
    """Validate the complete detached, path-free admission document."""

    try:
        root = _object(document, "review admission")
        _exact(root, _TOP, "review admission")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root["format_version"] != FORMAT_VERSION:
            raise BodySwayReviewAdmissionValidationError(
                "Body-sway review admission format is unsupported"
            )
        project = require_safe_token(root.get("project_id"), "Project id")
        require_safe_token(root.get("clip_id"), "Clip id")
        source = _source(root.get("source"), project)
        require_timing(root.get("timing"))
        require_body_sway_selection(root.get("selection"))
        visual = source["visual_review"]
        _head_observation(root.get("head_observation"), visual)
        _fixed(root.get("compiler"), compiler_profile(), "compiler")
        _fixed(root.get("claims"), admission_claims(), "claims")
        if root.get("status") != "admitted_for_safety_analysis":
            raise BodySwayReviewAdmissionValidationError(
                "Body-sway review admission status is unsupported"
            )
        _fixed(root.get("release_gate"), admission_release_gate(),
               "release gate")
        if _contains_path_key(root):
            raise BodySwayReviewAdmissionValidationError(
                "Body-sway review admission must remain path-free"
            )
        if len(_canonical(root)) > MAX_ADMISSION_DOCUMENT_BYTES:
            raise BodySwayReviewAdmissionValidationError(
                "Body-sway review admission exceeds its byte limit"
            )
    except BodySwayReviewAdmissionValidationError:
        raise
    except (
        BodySwayProbeValidationError, IdleBehaviorDecisionFieldError,
        LayerManifestError, KeyError, OverflowError, RecursionError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayReviewAdmissionValidationError(
            f"Body-sway review admission validation failed: {exc}"
        ) from exc


def body_sway_review_admission_sha256(
    document: Mapping[str, Any],
) -> str:
    """Return the canonical identity only after strict validation."""

    require_body_sway_review_admission(document)
    return canonical_sha256(document)


def _source(value: Any, project_id: str) -> Mapping[str, Any]:
    source = _object(value, "review admission source")
    _exact(source, _SOURCE, "review admission source")
    _p10_chain(source.get("p10_chain"))
    _capture(source.get("capture"), project_id)
    _visual(source.get("visual_review"))
    return source


def _p10_chain(value: Any) -> None:
    row = _object(value, "exact P10 chain")
    _exact(row, _CHAIN, "exact P10 chain")
    require_sha256(
        row.get("body_sway_probe_report_sha256"),
        "Body-sway probe report digest",
    )
    upstream = dict(row)
    upstream.pop("body_sway_probe_report_sha256")
    require_body_sway_source(upstream)


def _capture(value: Any, project_id: str) -> Mapping[str, Any]:
    row = _object(value, "runtime capture identity")
    _exact(row, _CAPTURE, "runtime capture identity")
    if row.get("project_id") != project_id:
        raise BodySwayReviewAdmissionValidationError(
            "Admission capture project differs from the document"
        )
    for field in _CAPTURE - {"project_id"}:
        require_sha256(row.get(field), f"Admission capture {field}")
    return row


def _visual(value: Any) -> Mapping[str, Any]:
    row = _object(value, "visual review identity")
    _exact(row, _VISUAL, "visual review identity")
    for field in _VISUAL - {"revision"}:
        require_sha256(row.get(field), f"Admission visual review {field}")
    revision = row.get("revision")
    if type(revision) is not int or not 1 <= revision <= 64 \
            or row["decision_sha256"] != row["head_decision_sha256"]:
        raise BodySwayReviewAdmissionValidationError(
            "Admission decision must be the observed visual-review head"
        )
    return row


def _head_observation(value: Any, visual: Mapping[str, Any]) -> None:
    row = _object(value, "head observation")
    expected = body_sway_review_head_observation(
        visual["revision"], visual["head_decision_sha256"]
    )
    _fixed(row, expected, "head observation")


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BodySwayReviewAdmissionValidationError(
            f"Body-sway {label} must be an object"
        )
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise BodySwayReviewAdmissionValidationError(
            f"Body-sway {label} fields are unsupported"
        )


def _fixed(value: Any, expected: Any, label: str) -> None:
    if _canonical(value) != _canonical(expected):
        raise BodySwayReviewAdmissionValidationError(
            f"Body-sway review admission {label} is unsupported"
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
