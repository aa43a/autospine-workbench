"""Capture-result checks and best-effort derived review-mount publication."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .p10_preview_v2_service import (
    compile_cached_body_sway_preview_v2_record,
)
from .p10_runtime_capture_v2_commands import (
    P10RuntimeCaptureV2CommandResult,
)
from .p10_visual_review_v2_mount_store import P10VisualReviewV2MountStore


def capture_result_matches(
    request: Mapping[str, Any], preview: Any, result: Any,
) -> bool:
    """Return whether one execution result exactly matches its confirmed input."""

    return type(result) is P10RuntimeCaptureV2CommandResult \
        and result.package_id == request["package_id"] \
        and result.project_id == preview.project_id \
        and result.clip_id == preview.clip_id \
        and result.temporary_preview_v2_sha256 \
            == preview.temporary_preview_v2_sha256 \
        and result.case_count == preview.case_count


def publish_visual_review_mount_best_effort(
    projects: Any, job_id: str, result: Any,
) -> None:
    """Publish replaceable acceleration without changing completed authority."""

    try:
        record = compile_cached_body_sway_preview_v2_record(
            projects, result.package_id,
        )
        preview = record.result
        if (
            preview.project_id,
            preview.clip_id,
            preview.temporary_preview_v2_sha256,
        ) != (
            result.project_id,
            result.clip_id,
            result.temporary_preview_v2_sha256,
        ):
            return
        P10VisualReviewV2MountStore(projects.state_root).save(
            job_id, record,
        )
    except Exception:
        return


__all__ = [
    "capture_result_matches",
    "publish_visual_review_mount_best_effort",
]
