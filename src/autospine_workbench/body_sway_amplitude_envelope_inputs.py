"""Exact in-memory admission for P10.4b1 amplitude-envelope candidates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .body_sway_preview_inputs import (
    BodySwayPreviewInputs,
    BodySwayPreviewInputError,
    require_body_sway_preview_inputs,
)
from .body_sway_preview_projection import (
    BodySwayPreviewProjection,
    BodySwayPreviewProjectionError,
    compile_body_sway_preview_projection,
)
from .body_sway_review_admission import BodySwayReviewAdmission
from .body_sway_review_admission_validation import (
    BodySwayReviewAdmissionValidationError,
    require_body_sway_review_admission,
)
from .temporary_body_sway_preview import TemporaryBodySwayPreview
from .temporary_body_sway_preview_validation import (
    TemporaryBodySwayPreviewValidationError,
    require_temporary_body_sway_preview,
)


class BodySwayAmplitudeEnvelopeInputError(ValueError):
    """Raised when reviewed evidence and its sampled preview diverge."""


@dataclass(frozen=True, slots=True)
class BodySwayAmplitudeEnvelopeInputs:
    """Frozen exact values admitted for candidate-only gain probing."""

    _admission: BodySwayReviewAdmission = field(repr=False)
    _preview_inputs: BodySwayPreviewInputs = field(repr=False)
    _preview: TemporaryBodySwayPreview = field(repr=False)
    _projection: BodySwayPreviewProjection = field(repr=False)

    @property
    def project_id(self) -> str:
        return self._admission.document["project_id"]

    @property
    def clip_id(self) -> str:
        return self._admission.document["clip_id"]

    @property
    def admission(self) -> BodySwayReviewAdmission:
        return self._admission

    @property
    def admission_document(self) -> dict[str, Any]:
        return self._admission.document

    @property
    def preview_inputs(self) -> BodySwayPreviewInputs:
        return self._preview_inputs

    @property
    def preview(self) -> TemporaryBodySwayPreview:
        return self._preview

    @property
    def projection(self) -> BodySwayPreviewProjection:
        return self._projection


def require_body_sway_amplitude_envelope_inputs(
    admission: BodySwayReviewAdmission,
    preview_inputs: BodySwayPreviewInputs,
    preview: TemporaryBodySwayPreview,
) -> BodySwayAmplitudeEnvelopeInputs:
    """Bind one approved review admission to its exact sampled preview."""

    try:
        if type(admission) is not BodySwayReviewAdmission \
                or type(preview_inputs) is not BodySwayPreviewInputs \
                or type(preview) is not TemporaryBodySwayPreview:
            raise BodySwayAmplitudeEnvelopeInputError(
                "Amplitude envelope requires exact admitted P10 values"
            )
        admission_document = admission.document
        require_body_sway_review_admission(admission_document)
        rebuilt_inputs = require_body_sway_preview_inputs(
            preview_inputs.probe_inputs, preview_inputs.report
        )
        if rebuilt_inputs.report_sha256 != preview_inputs.report_sha256:
            raise BodySwayAmplitudeEnvelopeInputError(
                "Amplitude envelope preview inputs changed during replay"
            )
        preview_document = preview.document
        require_temporary_body_sway_preview(
            preview_document, preview.artifact_bytes
        )
        projection = compile_body_sway_preview_projection(preview_inputs)
        _require_exact_chain(
            admission_document, preview_document, preview, projection
        )
        return BodySwayAmplitudeEnvelopeInputs(
            admission, preview_inputs, preview, projection
        )
    except BodySwayAmplitudeEnvelopeInputError:
        raise
    except _FAILURES as exc:
        raise BodySwayAmplitudeEnvelopeInputError(
            f"Body-sway amplitude envelope input admission failed: {exc}"
        ) from exc


def _require_exact_chain(admission, preview_document, preview, projection):
    source = admission["source"]
    if admission["project_id"] != preview_document["project_id"] \
            or admission["clip_id"] != preview_document["clip_id"] \
            or admission["timing"] != preview_document["timing"] \
            or admission["selection"] != preview_document["selection"]:
        raise BodySwayAmplitudeEnvelopeInputError(
            "Review admission differs from its preview identity"
        )
    if source["p10_chain"] != preview_document["source"]:
        raise BodySwayAmplitudeEnvelopeInputError(
            "Review admission P10 chain differs from its preview"
        )
    capture = source["capture"]
    if capture["temporary_preview_sha256"] != preview.sha256 \
            or capture["preview_artifact_set_sha256"] \
                != preview.artifact_set_sha256:
        raise BodySwayAmplitudeEnvelopeInputError(
            "Review admission capture differs from its preview"
        )
    metadata = preview_document["projection"]
    if metadata["projection_sha256"] != projection.sha256 \
            or metadata["rotation_interpolation"] != "sampled-linear":
        raise BodySwayAmplitudeEnvelopeInputError(
            "Amplitude envelope requires the exact sampled-linear projection"
        )


_FAILURES = (
    AttributeError, BodySwayPreviewInputError,
    BodySwayPreviewProjectionError,
    BodySwayReviewAdmissionValidationError, KeyError, OverflowError,
    RecursionError, TemporaryBodySwayPreviewValidationError, TypeError,
    UnicodeError, ValueError,
)
