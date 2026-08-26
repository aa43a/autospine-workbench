"""Strict semantic validation for P10.3c visual-review candidates."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .body_sway_runtime_capture_collector import MAX_CAPTURE_BYTES
from .body_sway_runtime_capture_reader import VerifiedBodySwayRuntimeCapture
from .body_sway_visual_review_profile import (
    CANDIDATE_GENERATOR,
    CANDIDATE_RELEASE_GATE,
    CANDIDATE_SEMANTICS,
    MAX_VISUAL_REVIEW_DOCUMENT_BYTES,
    body_sway_browser_profile_sha256,
    body_sway_case_evidence_sha256,
)
from .manifest_artifacts import (
    LayerManifestError,
    require_safe_token,
    require_sha256,
)
from .resolved_project import canonical_sha256


FORMAT = "autospine-body-sway-visual-review-candidate"
FORMAT_VERSION = 1
_TOP = {
    "format", "format_version", "project_id", "clip_id", "source",
    "generator", "semantics", "cases", "status", "release_gate", "summary",
}
_SOURCE = {
    "runtime_capture_manifest_sha256", "runtime_capture_bundle_sha256",
    "temporary_preview_sha256", "capture_artifact_set_sha256",
    "capture_case_stream_sha256", "browser_profile_sha256",
}
_CASE = {
    "case_id", "animation", "tick", "time_seconds", "image",
    "evidence_sha256",
}
_IMAGE = {
    "path", "png_sha256", "size_bytes", "width", "height",
}


class BodySwayVisualReviewCandidateValidationError(ValueError):
    """Raised when a sampled visual-review candidate is incomplete or stale."""


def require_body_sway_visual_review_candidate(
    document: Mapping[str, Any], *,
    capture: VerifiedBodySwayRuntimeCapture | None = None,
) -> None:
    """Validate standalone seals and optionally the exact capture binding."""

    try:
        root = _object(document, "Visual review candidate")
        _exact(root, _TOP, "Visual review candidate")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root.get("format_version") != FORMAT_VERSION:
            raise BodySwayVisualReviewCandidateValidationError(
                "Visual review candidate format is unsupported"
            )
        require_safe_token(root.get("project_id"), "Visual review project id")
        require_safe_token(root.get("clip_id"), "Visual review clip id")
        _source(root.get("source"))
        _fixed(root.get("generator"), CANDIDATE_GENERATOR, "generator")
        _fixed(root.get("semantics"), CANDIDATE_SEMANTICS, "semantics")
        cases = _cases(root.get("cases"))
        if root.get("status") != "candidate_only":
            raise BodySwayVisualReviewCandidateValidationError(
                "Visual review candidate must remain candidate_only"
            )
        _fixed(root.get("release_gate"), CANDIDATE_RELEASE_GATE, "release gate")
        summary = _object(root.get("summary"), "Visual review candidate summary")
        expected_summary = {
            "case_count": len(cases),
            "pending_count": len(cases),
            "status": "candidate_only",
        }
        if dict(summary) != expected_summary:
            raise BodySwayVisualReviewCandidateValidationError(
                "Visual review candidate summary is inconsistent"
            )
        if capture is not None:
            _capture_binding(root, capture)
        if len(_canonical(root)) > MAX_VISUAL_REVIEW_DOCUMENT_BYTES:
            raise BodySwayVisualReviewCandidateValidationError(
                "Visual review candidate exceeds its byte limit"
            )
    except BodySwayVisualReviewCandidateValidationError:
        raise
    except (
        LayerManifestError, KeyError, OverflowError, RecursionError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayVisualReviewCandidateValidationError(
            f"Visual review candidate validation failed: {exc}"
        ) from exc


def body_sway_visual_review_candidate_sha256(
    document: Mapping[str, Any],
) -> str:
    require_body_sway_visual_review_candidate(document)
    return canonical_sha256(document)


def body_sway_visual_review_source(
    capture: VerifiedBodySwayRuntimeCapture,
) -> dict[str, str]:
    """Derive every exact upstream identity copied into one candidate."""

    if type(capture) is not VerifiedBodySwayRuntimeCapture:
        raise BodySwayVisualReviewCandidateValidationError(
            "Visual review requires an exact verified capture"
        )
    document = capture.capture.document
    return {
        "runtime_capture_manifest_sha256": capture.capture.sha256,
        "runtime_capture_bundle_sha256": capture.bundle_sha256,
        "temporary_preview_sha256": document["source"][
            "temporary_preview_sha256"
        ],
        "capture_artifact_set_sha256": document["artifacts"][
            "artifact_set_sha256"
        ],
        "capture_case_stream_sha256": document["capture"][
            "case_stream_sha256"
        ],
        "browser_profile_sha256": body_sway_browser_profile_sha256(document),
    }


def visual_review_case_rows(
    capture: VerifiedBodySwayRuntimeCapture,
) -> list[dict[str, Any]]:
    """Derive ordered, per-PNG review evidence from an exact capture."""

    document = capture.capture.document
    files = {row["case_id"]: row for row in document["artifacts"]["files"]}
    rows = []
    for captured_case in document["cases"]:
        artifact = files[captured_case["case_id"]]
        rows.append({
            "case_id": captured_case["case_id"],
            "animation": captured_case["animation"],
            "tick": captured_case["tick"],
            "time_seconds": captured_case["time_seconds"],
            "image": {
                "path": artifact["path"],
                "png_sha256": artifact["sha256"],
                "size_bytes": artifact["size_bytes"],
                "width": artifact["width"],
                "height": artifact["height"],
            },
            "evidence_sha256": body_sway_case_evidence_sha256(
                captured_case, artifact
            ),
        })
    return rows


def _capture_binding(root, capture) -> None:
    expected_source = body_sway_visual_review_source(capture)
    expected_cases = visual_review_case_rows(capture)
    capture_document = capture.capture.document
    if root["project_id"] != capture_document["project_id"] \
            or root["clip_id"] != capture_document["clip_id"] \
            or root["source"] != expected_source \
            or root["cases"] != expected_cases:
        raise BodySwayVisualReviewCandidateValidationError(
            "Visual review candidate differs from its exact runtime capture"
        )


def _source(value: Any) -> None:
    row = _object(value, "Visual review candidate source")
    _exact(row, _SOURCE, "Visual review candidate source")
    for field in _SOURCE:
        require_sha256(row.get(field), field)


def _cases(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not 3 <= len(value) <= 55:
        raise BodySwayVisualReviewCandidateValidationError(
            "Visual review candidate case count is invalid"
        )
    result = []
    ids, paths = set(), set()
    for raw in value:
        row = _object(raw, "Visual review candidate case")
        _exact(row, _CASE, "Visual review candidate case")
        case_id = require_safe_token(row.get("case_id"), "Visual review case id")
        animation = row.get("animation")
        if animation is not None:
            require_safe_token(animation, "Visual review animation")
        tick = row.get("tick")
        time_seconds = row.get("time_seconds")
        if type(tick) is not int or not 0 <= tick <= 600_000_000 \
                or isinstance(time_seconds, bool) \
                or not isinstance(time_seconds, (int, float)) \
                or not 0 <= float(time_seconds) <= 600.0:
            raise BodySwayVisualReviewCandidateValidationError(
                "Visual review case timing is invalid"
            )
        image = _image(row.get("image"), case_id)
        require_sha256(row.get("evidence_sha256"), "Case evidence digest")
        if row["evidence_sha256"] != _row_evidence_sha256(row, image):
            raise BodySwayVisualReviewCandidateValidationError(
                "Visual review case evidence seal is inconsistent"
            )
        ids.add(case_id)
        paths.add(image["path"].casefold())
        result.append(row)
    if len(ids) != len(result) or len(paths) != len(result):
        raise BodySwayVisualReviewCandidateValidationError(
            "Visual review case ids and image paths must be unique"
        )
    return result


def _image(value: Any, case_id: str) -> Mapping[str, Any]:
    row = _object(value, "Visual review case image")
    _exact(row, _IMAGE, "Visual review case image")
    if row.get("path") != f"captures/{case_id}.png":
        raise BodySwayVisualReviewCandidateValidationError(
            "Visual review case image path is inconsistent"
        )
    require_sha256(row.get("png_sha256"), "Visual review PNG digest")
    if type(row.get("size_bytes")) is not int \
            or not 1 <= row["size_bytes"] <= MAX_CAPTURE_BYTES \
            or row.get("width") != 640 or row.get("height") != 640:
        raise BodySwayVisualReviewCandidateValidationError(
            "Visual review case image metadata is invalid"
        )
    return row


def _row_evidence_sha256(row, image) -> str:
    captured_case = {
        "case_id": row["case_id"],
        "animation": row["animation"],
        "tick": row["tick"],
        "time_seconds": row["time_seconds"],
        "image_path": image["path"],
        "png_sha256": image["png_sha256"],
    }
    artifact = {
        "path": image["path"],
        "role": "official-runtime-capture",
        "case_id": row["case_id"],
        "sha256": image["png_sha256"],
        "size_bytes": image["size_bytes"],
        "width": image["width"],
        "height": image["height"],
    }
    return body_sway_case_evidence_sha256(captured_case, artifact)


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BodySwayVisualReviewCandidateValidationError(
            f"{label} must be an object"
        )
    return value


def _exact(value, fields, label) -> None:
    if set(value) != fields:
        raise BodySwayVisualReviewCandidateValidationError(
            f"{label} fields are unsupported"
        )


def _fixed(value, expected, label) -> None:
    if value != expected:
        raise BodySwayVisualReviewCandidateValidationError(
            f"Visual review candidate {label} is unsupported"
        )


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
