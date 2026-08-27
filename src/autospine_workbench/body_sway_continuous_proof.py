"""Pure compiler for BodySwayContinuousPreviewProof v1."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .body_sway_continuous_proof_analysis import (
    BodySwayContinuousProofAnalysisError,
    analyze_body_sway_continuous_source,
)
from .body_sway_continuous_proof_inputs import (
    BodySwayContinuousProofInputError,
    BodySwayContinuousProofInputs,
    require_body_sway_continuous_proof_inputs,
)
from .body_sway_continuous_proof_profile import (
    body_sway_continuous_proof_analyzer_profile,
    body_sway_continuous_proof_release_gate,
)
from .body_sway_continuous_proof_validation import (
    FORMAT,
    FORMAT_VERSION,
    BodySwayContinuousProofValidationError,
    require_body_sway_continuous_proof,
)


class BodySwayContinuousProofError(ValueError):
    """Raised when exact P10.4b1 sources cannot compile proof evidence."""


@dataclass(frozen=True, slots=True)
class BodySwayContinuousPreviewProof:
    """Frozen path-free proof evidence and its canonical identity."""

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


def compile_body_sway_continuous_preview_proof(
    inputs: BodySwayContinuousProofInputs,
) -> BodySwayContinuousPreviewProof:
    """Compile all-segment proof evidence without granting release authority."""

    try:
        if type(inputs) is not BodySwayContinuousProofInputs:
            raise BodySwayContinuousProofError(
                "Continuous proof compilation requires exact admitted inputs"
            )
        admitted = require_body_sway_continuous_proof_inputs(
            inputs.amplitude_candidate, inputs.amplitude_inputs
        )
        analysis = analyze_body_sway_continuous_source(admitted.source).document
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "project_id": admitted.project_id,
            "clip_id": admitted.clip_id,
            "source": admitted.source,
            **analysis,
            "analyzer": body_sway_continuous_proof_analyzer_profile(),
            "release_gate": body_sway_continuous_proof_release_gate(
                analysis["status"]
                == "continuous_preview_model_structural_certified"
            ),
        }
        require_body_sway_continuous_proof(document)
        return BodySwayContinuousPreviewProof(_canonical(document))
    except BodySwayContinuousProofError:
        raise
    except (
        AttributeError, BodySwayContinuousProofAnalysisError,
        BodySwayContinuousProofInputError,
        BodySwayContinuousProofValidationError, KeyError, OverflowError,
        RecursionError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayContinuousProofError(
            f"Continuous proof compilation failed: {exc}"
        ) from exc


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))
