"""Resolve one completed capture job into current P10.3c v2 inputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .body_sway_runtime_execution_reader import (
    VerifiedBodySwayRuntimeExecutionNotFound,
    VerifiedBodySwayRuntimeExecutionReader,
    VerifiedBodySwayRuntimeExecutionReaderError,
)
from .body_sway_visual_review_address_v2 import ExactVisualReviewAddressV2
from .manifest_artifacts import LayerManifestError, require_sha256
from .p10_capture_job_contract import (
    P10CaptureJobContractError, P10CaptureJobRequest,
)
from .p10_capture_job_manager import (
    P10CaptureJobManager, P10CaptureJobManagerError,
)
from .p10_capture_job_store import P10CaptureJobStoreError
from .p10_completed_job_snapshot import (
    P10CompletedJobSnapshotError, VerifiedCompletedP10CaptureJob,
    verified_completed_p10_capture_job,
)
from .p10_preview_v2_result import P10PreviewV2CommandError
from .p10_preview_v2_service import (
    compile_cached_body_sway_preview_v2_record,
    p10_preview_v2_cache_locator,
)
from .p10_visual_review_v2_mount_current import (
    P10VisualReviewV2MountCurrentError,
    require_current_p10_visual_review_v2_mount,
)
from .p10_visual_review_v2_mount_store import (
    P10VisualReviewV2MountStore,
    P10VisualReviewV2MountStoreError,
)
from .p10_visual_review_v2_verified_mount import (
    P10VisualReviewV2VerifiedMountError,
    VerifiedP10VisualReviewV2Mount,
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
    preview: VerifiedP10VisualReviewV2Mount
    job_head_event_sha256: str
    job_event_count: int
    _completed_job: VerifiedCompletedP10CaptureJob = field(repr=False)

    def public_job(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "package_id": self.package_id,
            "project_id": self.preview.result.project_id,
            "clip_id": self.preview.result.clip_id,
            "case_count": self.preview.result.case_count,
        }


def resolve_p10_visual_review_v2_context(
    manager: P10CaptureJobManager,
    store: ProjectStore,
    job_id: str,
    *,
    allow_acceleration: bool = True,
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
        completed_job = verified_completed_p10_capture_job(
            snapshot, expected_job,
        )
    except P10CompletedJobSnapshotError as exc:
        raise P10VisualReviewV2JobNotFound(
            "Runtime capture job snapshot is invalid"
        ) from exc
    try:
        address = completed_job.address
        if type(allow_acceleration) is not bool:
            raise ValueError("acceleration policy is invalid")
        execution = VerifiedBodySwayRuntimeExecutionReader(
            store.state_root,
        ).load(*address.reader_arguments)
        preview_artifact_sha = execution.execution.document["source"][
            "preview_artifact_set_sha256"
        ]
        record = _resolve_record(
            store, expected_job, request.document["package_id"], address,
            preview_artifact_sha, allow_acceleration=allow_acceleration,
        )
        _require_current(request.document, address, record.result)
        preview = VerifiedP10VisualReviewV2Mount.from_verified_record(
            record, execution,
        )
    except VerifiedBodySwayRuntimeExecutionNotFound as exc:
        raise P10VisualReviewV2JobNotFound(
            "Runtime capture execution is unavailable"
        ) from exc
    except (
        KeyError, P10PreviewV2CommandError,
        P10VisualReviewV2MountCurrentError,
        P10VisualReviewV2MountStoreError,
        P10VisualReviewV2VerifiedMountError,
        TypeError, ValueError,
        VerifiedBodySwayRuntimeExecutionReaderError,
    ) as exc:
        raise P10VisualReviewV2SourceChanged(
            "Current P10.1 or capture framing differs from the completed job"
        ) from exc
    return P10VisualReviewV2Context(
        completed_job.job_id, completed_job.package_id, address, preview,
        completed_job.terminal_event_sha256,
        completed_job.terminal_sequence, completed_job,
    )


def _resolve_record(
    store, job_id, package_id, address, preview_artifact_sha, *,
    allow_acceleration,
):
    locator = p10_preview_v2_cache_locator(store, package_id)
    cache = P10VisualReviewV2MountStore(store.state_root)
    record = None
    if allow_acceleration:
        try:
            record = cache.load(
                job_id, locator,
                expected_preview_sha256=address.temporary_preview_v2_sha256,
                expected_artifact_set_sha256=preview_artifact_sha,
            )
        except P10VisualReviewV2MountStoreError:
            record = None
    if record is not None:
        require_current_p10_visual_review_v2_mount(store, record)
        return record
    record = compile_cached_body_sway_preview_v2_record(store, package_id)
    if record.result.project_id != address.project_id \
            or record.result.temporary_preview_v2_sha256 \
                != address.temporary_preview_v2_sha256 \
            or record.result.artifact_set_sha256 != preview_artifact_sha:
        raise P10VisualReviewV2MountCurrentError(
            "Compiled mount differs from the completed execution"
        )
    if allow_acceleration:
        try:
            cache.save(job_id, record)
        except P10VisualReviewV2MountStoreError:
            pass
    return record


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
