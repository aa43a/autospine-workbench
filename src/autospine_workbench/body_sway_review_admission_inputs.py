"""Strict in-memory admission for one approved P10 sampled visual head."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any

from .body_sway_runtime_capture_binding import (
    BodySwayRuntimeCaptureBindingError,
    require_internally_valid_runtime_capture,
)
from .body_sway_runtime_capture_reader import VerifiedBodySwayRuntimeCapture
from .body_sway_visual_review_address import ExactVisualReviewAddress
from .body_sway_visual_review_application_models import (
    ExactBodySwayVisualReviewDecision,
    PreparedBodySwayVisualReview,
)
from .body_sway_visual_review_history_snapshot import (
    BodySwayVisualReviewHistorySnapshot,
)
from .body_sway_review_admission_input_checks import (
    BodySwayReviewAdmissionInputCheckError,
    require_body_sway_review_admission_input_content,
)
from .temporary_body_sway_preview import TemporaryBodySwayPreview
from .temporary_body_sway_preview_validation import (
    TemporaryBodySwayPreviewValidationError,
    require_temporary_body_sway_preview,
)


class BodySwayReviewAdmissionInputError(ValueError):
    """Raised when preview and current visual head are not one exact chain."""


@dataclass(frozen=True, slots=True)
class BodySwayReviewAdmissionInput:
    """Detached snapshots admitted only for compile-time contract generation."""

    address: ExactVisualReviewAddress
    visual_candidate_sha256: str
    visual_revision: int
    visual_decision_sha256: str
    history_before: BodySwayVisualReviewHistorySnapshot
    history_after: BodySwayVisualReviewHistorySnapshot
    _capture: VerifiedBodySwayRuntimeCapture = field(repr=False)
    _preview_json: str = field(repr=False)
    _preview_artifact_items: tuple[tuple[str, bytes], ...] = field(repr=False)
    _candidate_json: str = field(repr=False)
    _decision_json: str = field(repr=False)

    @property
    def project_id(self) -> str:
        return self.preview_document["project_id"]

    @property
    def clip_id(self) -> str:
        return self.preview_document["clip_id"]

    @property
    def preview_document(self) -> dict[str, Any]:
        return json.loads(self._preview_json)

    @property
    def candidate_document(self) -> dict[str, Any]:
        return json.loads(self._candidate_json)

    @property
    def decision_document(self) -> dict[str, Any]:
        return json.loads(self._decision_json)

    @property
    def source(self) -> dict[str, Any]:
        return dict(self.preview_document["source"])

    @property
    def timing(self) -> dict[str, Any]:
        return dict(self.preview_document["timing"])

    @property
    def selection(self) -> dict[str, Any]:
        return json.loads(_canonical(self.preview_document["selection"]))

    @property
    def runtime_capture_manifest_sha256(self) -> str:
        return self._capture.capture.sha256

def build_body_sway_review_admission_input(
    preview: TemporaryBodySwayPreview,
    capture: VerifiedBodySwayRuntimeCapture,
    before: PreparedBodySwayVisualReview,
    decision: ExactBodySwayVisualReviewDecision,
    after: PreparedBodySwayVisualReview,
    *,
    address: ExactVisualReviewAddress,
    candidate_sha256: str,
    revision: int,
    decision_sha256: str,
) -> BodySwayReviewAdmissionInput:
    """Snapshot exact application results and immediately revalidate them."""

    try:
        if type(preview) is not TemporaryBodySwayPreview \
                or type(capture) is not VerifiedBodySwayRuntimeCapture \
                or type(before) is not PreparedBodySwayVisualReview \
                or type(decision) is not ExactBodySwayVisualReviewDecision \
                or type(after) is not PreparedBodySwayVisualReview:
            raise BodySwayReviewAdmissionInputError(
                "Review admission requires exact application value objects"
            )
        value = BodySwayReviewAdmissionInput(
            address=address,
            visual_candidate_sha256=candidate_sha256,
            visual_revision=revision,
            visual_decision_sha256=decision_sha256,
            history_before=before.history,
            history_after=after.history,
            _capture=capture,
            _preview_json=_canonical(preview.document),
            _preview_artifact_items=tuple(sorted(preview.artifact_bytes.items())),
            _candidate_json=_canonical(before.candidate_document),
            _decision_json=_canonical(decision.decision_document),
        )
        if before.address != address or decision.address != address \
                or after.address != address \
                or before.candidate_sha256 != candidate_sha256 \
                or decision.candidate_sha256 != candidate_sha256 \
                or after.candidate_sha256 != candidate_sha256 \
                or decision.revision != revision \
                or decision.decision_sha256 != decision_sha256 \
                or before.candidate_document != after.candidate_document:
            raise BodySwayReviewAdmissionInputError(
                "Review application snapshots differ from explicit addresses"
            )
        return require_body_sway_review_admission_input(value)
    except BodySwayReviewAdmissionInputError:
        raise
    except _FAILURES as exc:
        raise BodySwayReviewAdmissionInputError(
            f"Body-sway review input build failed: {exc}"
        ) from exc


def require_body_sway_review_admission_input(
    value: BodySwayReviewAdmissionInput,
) -> BodySwayReviewAdmissionInput:
    """Revalidate all detached bytes and the stable approved head observation."""

    try:
        if type(value) is not BodySwayReviewAdmissionInput \
                or type(value.address) is not ExactVisualReviewAddress:
            raise BodySwayReviewAdmissionInputError(
                "Review admission input has the wrong representation"
            )
        preview = TemporaryBodySwayPreview(
            value._preview_json, value._preview_artifact_items
        )
        require_internally_valid_runtime_capture(value._capture)
        require_temporary_body_sway_preview(
            preview.document, preview.artifact_bytes
        )
        require_body_sway_review_admission_input_content(value, preview)
        return value
    except BodySwayReviewAdmissionInputError:
        raise
    except _FAILURES as exc:
        raise BodySwayReviewAdmissionInputError(
            f"Body-sway review input admission failed: {exc}"
        ) from exc


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )


_FAILURES = (
    AttributeError, BodySwayRuntimeCaptureBindingError,
    BodySwayReviewAdmissionInputCheckError, KeyError,
    OverflowError, RecursionError, RuntimeError,
    TemporaryBodySwayPreviewValidationError, TypeError, UnicodeError,
    ValueError,
)
