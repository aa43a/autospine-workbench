"""Resolve one completed capture job into current P10.3c v2 inputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .body_sway_visual_review_address_v2 import ExactVisualReviewAddressV2
from .manifest_artifacts import LayerManifestError, require_sha256
from .p10_capture_job_contract import (
    P10CaptureJobContractError, P10CaptureJobRequest,
)
from .p10_capture_job_manager import (
    P10CaptureJobManager, P10CaptureJobManagerError,
)
from .p10_capture_job_store import P10CaptureJobStoreError
from .p10_preview_v2_commands import (
    P10PreviewV2CommandError, P10PreviewV2CommandResult,
    compile_body_sway_preview_v2_for_package,
)
from .project_store import ProjectStore


class P10VisualReviewV2ContextError(RuntimeError):
    """Raised when a job cannot safely identify current review evidence."""


class P10VisualReviewV2JobNotFound(P10VisualReviewV2ContextError):
    pass


class P10VisualReviewV2JobIncomplete(P10VisualReviewV2ContextError):
    pass


class P10VisualReviewV2SourceChanged(P10VisualReviewV2ContextError):
    pass


@dataclass(frozen=True, slots=True)
class P10VisualReviewV2Context:
    job_id: str
    package_id: str
    address: ExactVisualReviewAddressV2
    preview: P10PreviewV2CommandResult

    def public_job(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "package_id": self.package_id,
            "project_id": self.preview.project_id,
            "clip_id": self.preview.clip_id,
            "case_count": self.preview.case_count,
        }


def resolve_p10_visual_review_v2_context(
    manager: P10CaptureJobManager,
    store: ProjectStore,
    job_id: str,
) -> P10VisualReviewV2Context:
    """Require a completed immutable job and replay its current package."""

    try:
        expected_job = require_sha256(job_id, "Runtime capture job")
    except LayerManifestError as exc:
        raise P10VisualReviewV2JobNotFound(
            "Runtime capture job id is invalid"
        ) from exc
    try:
        snapshot = manager.get(expected_job)
    except (P10CaptureJobManagerError, P10CaptureJobStoreError) as exc:
        raise P10VisualReviewV2JobNotFound(
            "Runtime capture job is unavailable"
        ) from exc
    request = _request(snapshot, expected_job)
    if snapshot.get("status") != "completed" \
            or snapshot.get("terminal") is not True \
            or snapshot.get("retryable") is not False:
        raise P10VisualReviewV2JobIncomplete(
            "Runtime capture job has not completed"
        )
    try:
        addresses = snapshot["addresses"]
        if type(addresses) is not dict or set(addresses) != {
            "project", "preview", "execution_bundle", "artifact",
        }:
            raise ValueError("address fields differ")
        address = ExactVisualReviewAddressV2(
            addresses["project"], addresses["preview"],
            addresses["execution_bundle"], addresses["artifact"],
        )
        preview = compile_body_sway_preview_v2_for_package(
            store, request.document["package_id"],
        )
        _require_current(request.document, address, preview)
    except (KeyError, TypeError, ValueError, P10PreviewV2CommandError) as exc:
        raise P10VisualReviewV2SourceChanged(
            "Current P10.1 or capture framing differs from the completed job"
        ) from exc
    return P10VisualReviewV2Context(
        expected_job, request.document["package_id"], address, preview,
    )


def _request(snapshot, job_id):
    try:
        if type(snapshot) is not dict or snapshot.get("job_id") != job_id:
            raise ValueError("job identity differs")
        public = snapshot["request"]
        if type(public) is not dict or public.get("job_id") != job_id:
            raise ValueError("request identity differs")
        document = {key: value for key, value in public.items()
                    if key != "job_id"}
        request = P10CaptureJobRequest.from_document(document)
        if request.job_id != job_id:
            raise ValueError("request hash differs")
        return request
    except (KeyError, TypeError, ValueError,
            P10CaptureJobContractError) as exc:
        raise P10VisualReviewV2JobNotFound(
            "Runtime capture job snapshot is invalid"
        ) from exc


def _require_current(request, address, preview):
    source = preview.document["source"]
    p10 = source["current_p10_1_head"]
    framing = {
        "candidate_sha256": preview.capture_framing_candidate_sha256,
        "decision_sha256": preview.capture_framing_decision_sha256,
        "revision": preview.capture_framing_revision,
    }
    if preview.project_id != address.project_id \
            or preview.temporary_preview_v2_sha256 \
                != address.temporary_preview_v2_sha256 \
            or request["expected_p10_1"] != p10 \
            or request["expected_framing"] != framing:
        raise ValueError("current source heads differ")


__all__ = [
    "P10VisualReviewV2Context", "P10VisualReviewV2ContextError",
    "P10VisualReviewV2JobIncomplete", "P10VisualReviewV2JobNotFound",
    "P10VisualReviewV2SourceChanged",
    "resolve_p10_visual_review_v2_context",
]
