"""Sanitized read-only HTTP projection for P10.4a v2 admission."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable

from .body_sway_review_admission_inputs_v2 import (
    BodySwayReviewAdmissionInputV2Error,
)
from .body_sway_review_admission_v2 import BodySwayReviewAdmissionV2Error
from .manifest_artifacts import LayerManifestError
from .p10_review_admission_v2_commands import (
    P10ReviewAdmissionV2CommandError,
    compile_body_sway_review_admission_v2_for_job,
)
from .p10_visual_review_v2_context import (
    P10VisualReviewV2JobIncomplete,
    P10VisualReviewV2JobNotFound,
    P10VisualReviewV2SourceChanged,
)
from .p10_visual_review_v2_http_responses import (
    job_incomplete, not_found, source_changed,
)


SendJson = Callable[[int, Any], None]
_NO_CURRENT_HEAD = "Completed job has no current visual review v2 decision"


def send_body_sway_review_admission_v2(
    job_reader: Any, store: Any, job_id: str, send_json: SendJson,
) -> None:
    """Compile the current admission without publishing any new artifact."""

    try:
        result = compile_body_sway_review_admission_v2_for_job(
            job_reader, store, job_id,
        )
    except P10ReviewAdmissionV2CommandError as exc:
        _send_command_error(exc, send_json)
        return
    except Exception:
        _internal_error(send_json)
        return
    send_json(HTTPStatus.OK, _response(result))


def _response(result) -> dict[str, Any]:
    document = result.document
    return {
        "ok": True,
        "status": document["status"],
        "job": {
            "job_id": result.job_id,
            "package_id": result.package_id,
            "terminal_event_sha256": result.terminal_event_sha256,
            "terminal_sequence": result.terminal_sequence,
        },
        "project_id": result.project_id,
        "clip_id": result.clip_id,
        "admission_sha256": result.admission_sha256,
        "inputs": {
            "temporary_preview_v2_sha256":
                result.temporary_preview_v2_sha256,
            "runtime_execution_sha256": result.runtime_execution_sha256,
            "runtime_execution_bundle_sha256":
                result.runtime_execution_bundle_sha256,
            "capture_artifact_set_sha256":
                result.capture_artifact_set_sha256,
            "visual_candidate_sha256": result.visual_candidate_sha256,
            "visual_revision": result.visual_revision,
            "visual_decision_sha256": result.visual_decision_sha256,
        },
        "claims": document["claims"],
        "release_gate": document["release_gate"],
        "document": document,
    }


def _send_command_error(exc, send_json) -> None:
    if _caused_by(exc, P10VisualReviewV2JobNotFound) \
            or _caused_by(exc, LayerManifestError):
        not_found(send_json)
    elif _caused_by(exc, P10VisualReviewV2JobIncomplete):
        job_incomplete(send_json)
    elif _caused_by(exc, P10VisualReviewV2SourceChanged):
        source_changed(send_json)
    elif str(exc) == _NO_CURRENT_HEAD or _caused_by(
        exc, (BodySwayReviewAdmissionInputV2Error,
              BodySwayReviewAdmissionV2Error),
    ):
        _not_ready(send_json)
    else:
        _internal_error(send_json)


def _caused_by(exc: BaseException, kinds) -> bool:
    current: BaseException | None = exc
    seen: set[int] = set()
    for _ in range(8):
        if current is None or id(current) in seen:
            return False
        if isinstance(current, kinds):
            return True
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return False


def _not_ready(send_json: SendJson) -> None:
    send_json(HTTPStatus.CONFLICT, {
        "error": "body_sway_review_admission_v2_not_ready",
        "message": (
            "A current sampled_visual_approved v2 head is required."
        ),
    })


def _internal_error(send_json: SendJson) -> None:
    send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {
        "error": "body_sway_review_admission_v2_error",
        "message": "The P10.4a v2 admission could not be compiled safely.",
    })


__all__ = ["send_body_sway_review_admission_v2"]
