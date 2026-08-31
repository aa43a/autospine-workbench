"""Exact execution and current Preview v2 bindings for review candidates."""

from __future__ import annotations

from typing import Any

from .body_sway_runtime_execution_bundle import (
    build_body_sway_runtime_execution_bundle,
)
from .body_sway_runtime_execution_reader import (
    VerifiedBodySwayRuntimeExecution,
)
from .body_sway_visual_review_profile_v2 import (
    body_sway_browser_profile_sha256_v2,
    body_sway_case_evidence_sha256_v2,
)
from .temporary_body_sway_preview_v2 import TemporaryBodySwayPreviewV2
from .temporary_body_sway_preview_validation_v2 import (
    require_temporary_body_sway_preview_v2,
)


class BodySwayVisualReviewCandidateSourceV2Error(ValueError):
    """Raised when execution evidence and the current preview diverge."""


def require_verified_visual_review_execution_v2(value):
    if type(value) is not VerifiedBodySwayRuntimeExecution:
        raise BodySwayVisualReviewCandidateSourceV2Error(
            "Visual review candidate v2 requires a verified execution"
        )
    built = build_body_sway_runtime_execution_bundle(value.execution)
    if built.bundle_sha256 != value.bundle_sha256 \
            or built.artifact_set_sha256 != value.artifact_set_sha256:
        raise BodySwayVisualReviewCandidateSourceV2Error(
            "Verified execution differs from its bundle identities"
        )
    return value


def body_sway_visual_review_source_v2(execution) -> dict[str, Any]:
    verified = require_verified_visual_review_execution_v2(execution)
    outer = verified.execution.document
    inner = verified.execution.capture.document
    source = outer["source"]
    return {
        "runtime_execution_sha256": verified.execution.sha256,
        "runtime_execution_bundle_sha256": verified.bundle_sha256,
        "runtime_capture_v2_sha256": source["runtime_capture_v2_sha256"],
        "temporary_preview_v2_sha256": source["temporary_preview_v2_sha256"],
        "preview_artifact_set_sha256": source["preview_artifact_set_sha256"],
        "capture_artifact_set_sha256": verified.artifact_set_sha256,
        "runtime_session_set_v2_sha256":
            source["runtime_session_set_v2_sha256"],
        "capture_plan_v2_sha256": source["capture_plan_v2_sha256"],
        "capture_case_stream_sha256": inner["capture"]["case_stream_sha256"],
        "browser_profile_sha256": body_sway_browser_profile_sha256_v2(outer),
        "capture_framing_candidate_sha256":
            source["capture_framing_candidate_sha256"],
        "capture_framing_decision_sha256":
            source["capture_framing_decision_sha256"],
        "capture_framing_revision": source["capture_framing_revision"],
        "body_sway_probe_report_sha256":
            source["body_sway_probe_report_sha256"],
        "current_p10_1_head": source["current_p10_1_head"],
        "world_viewport": source["world_viewport"],
    }


def visual_review_case_rows_v2(execution) -> list[dict[str, Any]]:
    verified = require_verified_visual_review_execution_v2(execution)
    document = verified.execution.capture.document
    files = {row["case_id"]: row for row in document["artifacts"]["files"]}
    return [{
        "case_id": case["case_id"], "animation": case["animation"],
        "tick": case["tick"], "time_seconds": case["time_seconds"],
        "image": {
            "path": files[case["case_id"]]["path"],
            "png_sha256": files[case["case_id"]]["sha256"],
            "size_bytes": files[case["case_id"]]["size_bytes"],
            "width": files[case["case_id"]]["width"],
            "height": files[case["case_id"]]["height"],
        },
        "evidence_sha256": body_sway_case_evidence_sha256_v2(
            case, files[case["case_id"]],
        ),
    } for case in document["cases"]]


def require_visual_review_candidate_source_binding_v2(
    root, execution, preview,
) -> None:
    verified = require_verified_visual_review_execution_v2(execution)
    if type(preview) is not TemporaryBodySwayPreviewV2:
        raise BodySwayVisualReviewCandidateSourceV2Error(
            "Visual review candidate v2 requires exact Preview v2"
        )
    require_temporary_body_sway_preview_v2(
        preview.document, preview.artifact_bytes,
    )
    outer = verified.execution.document
    preview_source = preview.document["source"]
    expected = {
        "temporary_preview_v2_sha256": preview.sha256,
        "preview_artifact_set_sha256": preview.artifact_set_sha256,
        "capture_framing_candidate_sha256":
            preview_source["capture_framing_candidate_sha256"],
        "capture_framing_decision_sha256":
            preview_source["capture_framing_decision_sha256"],
        "capture_framing_revision": preview_source["capture_framing_revision"],
        "body_sway_probe_report_sha256":
            preview_source["body_sway_probe_report_sha256"],
        "current_p10_1_head": preview_source["current_p10_1_head"],
        "world_viewport": preview.document["capture_plan"]["world_viewport"],
    }
    if root["project_id"] != preview.document["project_id"] \
            or root["clip_id"] != preview.document["clip_id"] \
            or any(outer["source"].get(field) != value
                   for field, value in expected.items()) \
            or root["source"] != body_sway_visual_review_source_v2(verified) \
            or root["cases"] != visual_review_case_rows_v2(verified):
        raise BodySwayVisualReviewCandidateSourceV2Error(
            "Visual review candidate v2 differs from current execution/preview"
        )


__all__ = [
    "BodySwayVisualReviewCandidateSourceV2Error",
    "body_sway_visual_review_source_v2",
    "require_verified_visual_review_execution_v2",
    "require_visual_review_candidate_source_binding_v2",
    "visual_review_case_rows_v2",
]
