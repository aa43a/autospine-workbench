"""Exact in-memory admission for P10.4b2 continuous proof compilation."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any

from .body_sway_amplitude_envelope import (
    BodySwayAmplitudeEnvelopeCandidate,
    compile_body_sway_amplitude_envelope_candidate,
)
from .body_sway_amplitude_envelope_inputs import (
    BodySwayAmplitudeEnvelopeInputs,
    require_body_sway_amplitude_envelope_inputs,
)
from .body_sway_continuous_proof_source import (
    BodySwayContinuousSourceError,
    build_body_sway_continuous_source,
)


class BodySwayContinuousProofInputError(ValueError):
    """Raised when a P10.4b2 source is stale, detached, or cross-wired."""


@dataclass(frozen=True, slots=True)
class BodySwayContinuousProofInputs:
    """Frozen exact P10.4b1 value plus its complete preview problem."""

    _amplitude_candidate: BodySwayAmplitudeEnvelopeCandidate = field(
        repr=False
    )
    _amplitude_inputs: BodySwayAmplitudeEnvelopeInputs = field(repr=False)
    _source_json: str = field(repr=False)

    @property
    def project_id(self) -> str:
        return self._amplitude_candidate.document["project_id"]

    @property
    def clip_id(self) -> str:
        return self._amplitude_candidate.document["clip_id"]

    @property
    def amplitude_candidate(self) -> BodySwayAmplitudeEnvelopeCandidate:
        return self._amplitude_candidate

    @property
    def amplitude_inputs(self) -> BodySwayAmplitudeEnvelopeInputs:
        return self._amplitude_inputs

    @property
    def source(self) -> dict[str, Any]:
        return json.loads(self._source_json)


def require_body_sway_continuous_proof_inputs(
    amplitude_candidate: BodySwayAmplitudeEnvelopeCandidate,
    amplitude_inputs: BodySwayAmplitudeEnvelopeInputs,
) -> BodySwayContinuousProofInputs:
    """Replay P10.4b1 and bind every exact continuous-proof source value."""

    try:
        if type(amplitude_candidate) is not BodySwayAmplitudeEnvelopeCandidate \
                or type(amplitude_inputs) is not BodySwayAmplitudeEnvelopeInputs:
            raise BodySwayContinuousProofInputError(
                "Continuous proof requires exact P10.4b1 in-memory values"
            )
        admitted = require_body_sway_amplitude_envelope_inputs(
            amplitude_inputs.admission,
            amplitude_inputs.preview_inputs,
            amplitude_inputs.preview,
        )
        rebuilt = compile_body_sway_amplitude_envelope_candidate(admitted)
        if rebuilt.canonical_bytes != amplitude_candidate.canonical_bytes:
            raise BodySwayContinuousProofInputError(
                "Continuous proof candidate differs from exact P10.4b1 replay"
            )
        probe = admitted.preview_inputs.probe_inputs
        source = build_body_sway_continuous_source(
            amplitude_candidate=rebuilt.document,
            rig=probe.rig,
            target_profile=probe.target_profile,
            motion_instance_v2=probe.motion_instance_v2,
            temporary_preview_manifest=admitted.preview.document,
            preview_projection=admitted.projection.document,
        )
        return BodySwayContinuousProofInputs(
            rebuilt, admitted, _canonical(source)
        )
    except BodySwayContinuousProofInputError:
        raise
    except (
        AttributeError, BodySwayContinuousSourceError, KeyError,
        OverflowError, RecursionError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayContinuousProofInputError(
            f"Continuous proof input admission failed: {exc}"
        ) from exc


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))
