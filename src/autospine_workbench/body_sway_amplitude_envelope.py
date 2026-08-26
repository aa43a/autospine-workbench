"""Pure compiler for BodySwayAmplitudeEnvelopeCandidate v1."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .body_sway_amplitude_envelope_analysis import (
    BodySwayAmplitudeEnvelopeAnalysisError,
    analyze_body_sway_amplitude_envelope,
)
from .body_sway_amplitude_envelope_inputs import (
    BodySwayAmplitudeEnvelopeInputError,
    BodySwayAmplitudeEnvelopeInputs,
    require_body_sway_amplitude_envelope_inputs,
)
from .body_sway_amplitude_envelope_profile import (
    body_sway_amplitude_envelope_analyzer_profile,
    body_sway_amplitude_envelope_claims,
    body_sway_amplitude_envelope_parameterization,
    body_sway_amplitude_envelope_release_gate,
)
from .body_sway_amplitude_envelope_validation import (
    FORMAT,
    FORMAT_VERSION,
    BodySwayAmplitudeEnvelopeValidationError,
    require_body_sway_amplitude_envelope_candidate,
)


class BodySwayAmplitudeEnvelopeError(ValueError):
    """Raised when exact reviewed inputs cannot form bounded candidates."""


@dataclass(frozen=True, slots=True)
class BodySwayAmplitudeEnvelopeCandidate:
    """Frozen path-free candidate bytes and their canonical identity."""

    _canonical_json: str = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


def compile_body_sway_amplitude_envelope_candidate(
    inputs: BodySwayAmplitudeEnvelopeInputs,
) -> BodySwayAmplitudeEnvelopeCandidate:
    """Compile sampled gain candidates without inferring a safe interval."""

    try:
        if type(inputs) is not BodySwayAmplitudeEnvelopeInputs:
            raise BodySwayAmplitudeEnvelopeError(
                "Amplitude envelope compilation requires exact admitted inputs"
            )
        admitted = require_body_sway_amplitude_envelope_inputs(
            inputs.admission, inputs.preview_inputs, inputs.preview
        )
        analysis = analyze_body_sway_amplitude_envelope(admitted).document
        admission = admitted.admission_document
        probes = analysis["probes"]
        statuses = [row["status"] for row in probes]
        reviewed = probes[-1]
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "project_id": admitted.project_id,
            "clip_id": admitted.clip_id,
            "source": {
                "review_admission_sha256": admitted.admission.sha256,
                "review_admission": admission,
                "reviewed_probe_report": admitted.preview_inputs.report,
            },
            "timing": _copy(admission["timing"]),
            "reviewed_selection": _copy(admission["selection"]),
            "parameterization": body_sway_amplitude_envelope_parameterization(
                admission["selection"]
            ),
            "probes": probes,
            "analyzer": body_sway_amplitude_envelope_analyzer_profile(),
            "claims": body_sway_amplitude_envelope_claims(),
            "status": "candidate_only",
            "release_gate": body_sway_amplitude_envelope_release_gate(),
            "summary": {
                "gain_probe_count": len(probes),
                "sampled_structural_passed_count": statuses.count(
                    "sampled_structural_passed"
                ),
                "sampled_structural_rejected_count": statuses.count(
                    "sampled_structural_rejected"
                ),
                "reviewed_gain_status": reviewed["status"],
                "sample_evaluation_count": sum(
                    row["sample_count"] for row in probes
                ),
            },
        }
        require_body_sway_amplitude_envelope_candidate(document)
        return BodySwayAmplitudeEnvelopeCandidate(_canonical(document))
    except BodySwayAmplitudeEnvelopeError:
        raise
    except _FAILURES as exc:
        raise BodySwayAmplitudeEnvelopeError(
            f"Body-sway amplitude envelope compilation failed: {exc}"
        ) from exc


def _copy(value: Any) -> Any:
    return json.loads(_canonical(value))


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )


_FAILURES = (
    AttributeError, BodySwayAmplitudeEnvelopeAnalysisError,
    BodySwayAmplitudeEnvelopeInputError,
    BodySwayAmplitudeEnvelopeValidationError, KeyError, OverflowError,
    RecursionError, TypeError, UnicodeError, ValueError,
)
