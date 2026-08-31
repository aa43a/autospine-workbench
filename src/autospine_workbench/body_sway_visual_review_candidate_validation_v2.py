"""Strict P10.3c v2 candidate validation against execution and Preview v2."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .body_sway_runtime_capture_collector import MAX_CAPTURE_BYTES
from .body_sway_runtime_execution_reader import (
    VerifiedBodySwayRuntimeExecution,
)
from .body_sway_visual_review_candidate_source_v2 import (
    BodySwayVisualReviewCandidateSourceV2Error,
    require_visual_review_candidate_source_binding_v2,
)
from .body_sway_visual_review_profile_v2 import (
    CANDIDATE_GENERATOR,
    CANDIDATE_RELEASE_GATE,
    CANDIDATE_SEMANTICS,
    MAX_VISUAL_REVIEW_DOCUMENT_BYTES,
    body_sway_case_evidence_sha256_v2,
)
from .manifest_artifacts import (
    LayerManifestError,
    require_safe_token,
    require_sha256,
)
from .resolved_project import canonical_sha256
from .temporary_body_sway_preview_v2 import TemporaryBodySwayPreviewV2


FORMAT = "autospine-body-sway-visual-review-candidate"
FORMAT_VERSION = 2
_TOP = {
    "format", "format_version", "project_id", "clip_id", "source",
    "generator", "semantics", "cases", "status", "release_gate", "summary",
}
_SOURCE_DIGESTS = {
    "runtime_execution_sha256", "runtime_execution_bundle_sha256",
    "runtime_capture_v2_sha256", "temporary_preview_v2_sha256",
    "preview_artifact_set_sha256", "capture_artifact_set_sha256",
    "runtime_session_set_v2_sha256", "capture_plan_v2_sha256",
    "capture_case_stream_sha256", "browser_profile_sha256",
    "capture_framing_candidate_sha256",
    "capture_framing_decision_sha256", "body_sway_probe_report_sha256",
}
_SOURCE = _SOURCE_DIGESTS | {
    "capture_framing_revision", "current_p10_1_head", "world_viewport",
}
_CASE = {
    "case_id", "animation", "tick", "time_seconds", "image",
    "evidence_sha256",
}
_IMAGE = {"path", "png_sha256", "size_bytes", "width", "height"}


class BodySwayVisualReviewCandidateV2ValidationError(ValueError):
    """Raised when a v2 candidate is incomplete, stale, or cross-wired."""


def require_body_sway_visual_review_candidate_v2(
    document: Mapping[str, Any], *,
    execution: VerifiedBodySwayRuntimeExecution | None = None,
    preview: TemporaryBodySwayPreviewV2 | None = None,
) -> None:
    """Validate detached seals and optionally exact execution/preview binding."""

    try:
        root = _object(document, "candidate")
        _exact(root, _TOP, "candidate")
        if root.get("format") != FORMAT \
                or root.get("format_version") != FORMAT_VERSION:
            raise BodySwayVisualReviewCandidateV2ValidationError(
                "Visual review candidate v2 format is unsupported"
            )
        require_safe_token(root.get("project_id"), "Visual review v2 project")
        require_safe_token(root.get("clip_id"), "Visual review v2 clip")
        require_body_sway_visual_review_source_v2(root.get("source"))
        _fixed(root.get("generator"), CANDIDATE_GENERATOR, "generator")
        _fixed(root.get("semantics"), CANDIDATE_SEMANTICS, "semantics")
        cases = _cases(root.get("cases"))
        if root.get("status") != "candidate_only":
            raise BodySwayVisualReviewCandidateV2ValidationError(
                "Visual review candidate v2 must remain candidate_only"
            )
        _fixed(root.get("release_gate"), CANDIDATE_RELEASE_GATE, "release gate")
        if root.get("summary") != {
            "case_count": len(cases), "pending_count": len(cases),
            "status": "candidate_only",
        }:
            raise BodySwayVisualReviewCandidateV2ValidationError(
                "Visual review candidate v2 summary is inconsistent"
            )
        if (execution is None) != (preview is None):
            raise BodySwayVisualReviewCandidateV2ValidationError(
                "Execution and Preview v2 must be validated together"
            )
        if execution is not None:
            require_visual_review_candidate_source_binding_v2(
                root, execution, preview,
            )
        if len(_canonical(root)) > MAX_VISUAL_REVIEW_DOCUMENT_BYTES:
            raise BodySwayVisualReviewCandidateV2ValidationError(
                "Visual review candidate v2 exceeds its byte limit"
            )
    except BodySwayVisualReviewCandidateV2ValidationError:
        raise
    except (
        BodySwayVisualReviewCandidateSourceV2Error,
        LayerManifestError, KeyError, OverflowError, RecursionError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayVisualReviewCandidateV2ValidationError(
            f"Visual review candidate v2 validation failed: {exc}"
        ) from exc


def body_sway_visual_review_candidate_sha256_v2(document) -> str:
    require_body_sway_visual_review_candidate_v2(document)
    return canonical_sha256(document)


def require_body_sway_visual_review_source_v2(value) -> None:
    row = _object(value, "source")
    _exact(row, _SOURCE, "source")
    for field in _SOURCE_DIGESTS:
        require_sha256(row.get(field), field)
    revision = row.get("capture_framing_revision")
    head = _object(row.get("current_p10_1_head"), "P10.1 head")
    viewport = _object(row.get("world_viewport"), "world viewport")
    if type(revision) is not int or not 1 <= revision <= 64 \
            or set(head) != {"candidate_sha256", "decision_sha256", "revision"} \
            or set(viewport) != {"x", "y", "width", "height"}:
        raise BodySwayVisualReviewCandidateV2ValidationError(
            "Visual review candidate v2 current source is invalid"
        )
    require_sha256(head.get("candidate_sha256"), "P10.0 candidate")
    require_sha256(head.get("decision_sha256"), "P10.1 decision")
    if type(head.get("revision")) is not int or not 1 <= head["revision"] <= 64:
        raise BodySwayVisualReviewCandidateV2ValidationError(
            "Visual review candidate v2 P10.1 revision is invalid"
        )
    if any(isinstance(viewport.get(key), bool)
           or not isinstance(viewport.get(key), (int, float))
           for key in viewport) or viewport["width"] <= 0 \
            or viewport["height"] <= 0:
        raise BodySwayVisualReviewCandidateV2ValidationError(
            "Visual review candidate v2 viewport is invalid"
        )


def _cases(value):
    if not isinstance(value, list) or not 3 <= len(value) <= 55:
        raise BodySwayVisualReviewCandidateV2ValidationError(
            "Visual review candidate v2 case count is invalid"
        )
    result, ids, paths = [], set(), set()
    for raw in value:
        row = _object(raw, "case")
        _exact(row, _CASE, "case")
        case_id = require_safe_token(row.get("case_id"), "Visual review v2 case")
        if row.get("animation") is not None:
            require_safe_token(row["animation"], "Visual review v2 animation")
        tick, seconds = row.get("tick"), row.get("time_seconds")
        if type(tick) is not int or not 0 <= tick <= 600_000_000 \
                or isinstance(seconds, bool) \
                or not isinstance(seconds, (int, float)) \
                or not 0 <= float(seconds) <= 600.0:
            raise BodySwayVisualReviewCandidateV2ValidationError(
                "Visual review candidate v2 case timing is invalid"
            )
        image = _image(row.get("image"), case_id)
        require_sha256(row.get("evidence_sha256"), "Visual evidence v2")
        if row["evidence_sha256"] != _row_evidence(row, image):
            raise BodySwayVisualReviewCandidateV2ValidationError(
                "Visual review candidate v2 evidence seal is inconsistent"
            )
        ids.add(case_id)
        paths.add(image["path"].casefold())
        result.append(row)
    if len(ids) != len(result) or len(paths) != len(result):
        raise BodySwayVisualReviewCandidateV2ValidationError(
            "Visual review candidate v2 case identities are duplicated"
        )
    return result


def _image(value, case_id):
    row = _object(value, "image")
    _exact(row, _IMAGE, "image")
    if row.get("path") != f"captures/{case_id}.png" \
            or type(row.get("size_bytes")) is not int \
            or not 1 <= row["size_bytes"] <= MAX_CAPTURE_BYTES \
            or (row.get("width"), row.get("height")) != (640, 640):
        raise BodySwayVisualReviewCandidateV2ValidationError(
            "Visual review candidate v2 image metadata is invalid"
        )
    require_sha256(row.get("png_sha256"), "Visual review v2 PNG")
    return row


def _row_evidence(row, image):
    case = {
        "case_id": row["case_id"], "animation": row["animation"],
        "tick": row["tick"], "time_seconds": row["time_seconds"],
        "image_path": image["path"], "png_sha256": image["png_sha256"],
    }
    artifact = {
        "path": image["path"], "role": "validated-runtime-capture-payload-v2",
        "case_id": row["case_id"], "sha256": image["png_sha256"],
        "size_bytes": image["size_bytes"], "width": image["width"],
        "height": image["height"],
    }
    return body_sway_case_evidence_sha256_v2(case, artifact)


def _object(value, label):
    if not isinstance(value, Mapping):
        raise BodySwayVisualReviewCandidateV2ValidationError(
            f"Visual review candidate v2 {label} must be an object"
        )
    return value


def _exact(value, fields, label):
    if set(value) != fields:
        raise BodySwayVisualReviewCandidateV2ValidationError(
            f"Visual review candidate v2 {label} fields are unsupported"
        )


def _fixed(value, expected, label):
    if value != expected:
        raise BodySwayVisualReviewCandidateV2ValidationError(
            f"Visual review candidate v2 {label} is unsupported"
        )


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8")
