"""Process-local proof that detached Preview v2 mount bytes were verified."""

from __future__ import annotations

from dataclasses import dataclass

from .body_sway_runtime_capture_v2 import (
    BodySwayRuntimeCaptureV2Error,
    require_body_sway_runtime_capture_v2_preview_binding,
)
from .body_sway_runtime_execution_reader import (
    VerifiedBodySwayRuntimeExecution,
)
from .p10_preview_v2_cache import P10PreviewV2CacheRecord
from .p10_preview_v2_result import P10PreviewV2CommandResult
from .temporary_body_sway_preview_validation_v2 import (
    TemporaryBodySwayPreviewValidationV2Error,
    require_temporary_body_sway_preview_v2,
)


class P10VisualReviewV2VerifiedMountError(RuntimeError):
    """Raised when a mount record cannot form a trusted process token."""


@dataclass(frozen=True, slots=True)
class VerifiedP10VisualReviewV2Mount:
    """A validated record; currentness remains the context resolver's duty."""

    record: P10PreviewV2CacheRecord
    execution: VerifiedBodySwayRuntimeExecution

    @classmethod
    def from_verified_record(
        cls, record: P10PreviewV2CacheRecord,
        execution: VerifiedBodySwayRuntimeExecution,
    ) -> "VerifiedP10VisualReviewV2Mount":
        try:
            if type(record) is not P10PreviewV2CacheRecord:
                raise P10VisualReviewV2VerifiedMountError(
                    "Visual review v2 mount record type is invalid"
                )
            if type(execution) is not VerifiedBodySwayRuntimeExecution:
                raise P10VisualReviewV2VerifiedMountError(
                    "Visual review v2 execution type is invalid"
                )
            result = record.result
            preview = result._preview
            require_temporary_body_sway_preview_v2(
                preview.document, preview.artifact_bytes,
            )
            source = preview.document["source"]
            p10 = source["current_p10_1_head"]
            expected = (
                record.address.package_id,
                record.address.project_id,
                record.address.clip_id,
                preview.sha256,
                preview.artifact_set_sha256,
                record.candidates.sha256,
                record.framing_candidate.sha256,
                p10["decision_sha256"], p10["revision"],
                source["capture_framing_decision_sha256"],
                source["capture_framing_revision"],
                preview.artifact_set_sha256,
            )
            actual = (
                result.package_id, result.project_id, result.clip_id,
                result.temporary_preview_v2_sha256,
                result.artifact_set_sha256,
                record.key.p10_candidate_sha256,
                result.capture_framing_candidate_sha256,
                record.key.p10_decision_sha256,
                record.key.p10_revision,
                result.capture_framing_decision_sha256,
                result.capture_framing_revision,
                execution.execution.document["source"][
                    "preview_artifact_set_sha256"
                ],
            )
            if actual != expected \
                    or source["idle_behavior_candidates_sha256"] \
                        != record.candidates.sha256:
                raise P10VisualReviewV2VerifiedMountError(
                    "Visual review v2 mount identities are cross-wired"
                )
            if execution.project_id != result.project_id \
                    or execution.temporary_preview_v2_sha256 \
                        != result.temporary_preview_v2_sha256:
                raise P10VisualReviewV2VerifiedMountError(
                    "Visual review v2 execution address differs"
                )
            require_body_sway_runtime_capture_v2_preview_binding(
                execution.execution.capture, preview,
            )
            return cls(record, execution)
        except P10VisualReviewV2VerifiedMountError:
            raise
        except (
            AttributeError, BodySwayRuntimeCaptureV2Error, KeyError,
            TemporaryBodySwayPreviewValidationV2Error,
            TypeError, ValueError,
        ) as exc:
            raise P10VisualReviewV2VerifiedMountError(
                "Visual review v2 mount bytes are invalid"
            ) from exc

    @property
    def result(self) -> P10PreviewV2CommandResult:
        return self.record.result

    @property
    def preview(self):
        return self.record.result._preview


__all__ = [
    "P10VisualReviewV2VerifiedMountError",
    "VerifiedP10VisualReviewV2Mount",
]
