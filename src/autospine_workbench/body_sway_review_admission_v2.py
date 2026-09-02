"""Pure canonical compiler for BodySwayReviewAdmission v2."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .body_sway_review_admission_inputs_v2 import (
    BodySwayReviewAdmissionInputV2,
    BodySwayReviewAdmissionInputV2Error,
    require_body_sway_review_admission_input_v2,
)
from .body_sway_review_admission_profile_v2 import (
    admission_claims_v2, admission_release_gate_v2,
    body_sway_review_head_observation_v2, compiler_profile_v2,
)
from .body_sway_review_admission_validation_v2 import (
    FORMAT, FORMAT_VERSION, BodySwayReviewAdmissionV2ValidationError,
    require_body_sway_review_admission_v2,
)


class BodySwayReviewAdmissionV2Error(ValueError):
    """Raised when exact P10.3c v2 evidence cannot form an admission."""


@dataclass(frozen=True, slots=True)
class BodySwayReviewAdmissionV2:
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


def compile_body_sway_review_admission_v2(
    inputs: BodySwayReviewAdmissionInputV2,
) -> BodySwayReviewAdmissionV2:
    """Admit only the approved v2 head seen around exact decision replay."""

    try:
        admitted = require_body_sway_review_admission_input_v2(inputs)
        address = admitted.address
        revision = admitted.visual_revision
        decision_sha = admitted.visual_decision_sha256
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "project_id": admitted.project_id,
            "clip_id": admitted.clip_id,
            "source": {
                "job": {
                    "job_id": admitted.job_id,
                    "package_id": admitted.package_id,
                    "terminal_event_sha256":
                        admitted.job_terminal_event_sha256,
                    "terminal_sequence": admitted.job_terminal_sequence,
                },
                "execution": {
                    "project_id": address.project_id,
                    "temporary_preview_v2_sha256":
                        address.temporary_preview_v2_sha256,
                    "runtime_execution_sha256":
                        admitted._execution.execution.sha256,
                    "runtime_execution_bundle_sha256":
                        address.runtime_execution_bundle_sha256,
                    "capture_artifact_set_sha256":
                        address.capture_artifact_set_sha256,
                },
                "preview_source": _copy(
                    admitted.preview_document["source"],
                ),
                "evidence": _copy(admitted.evidence),
                "visual_review": {
                    "candidate_v2_sha256":
                        admitted.visual_candidate_sha256,
                    "revision": revision,
                    "decision_v2_sha256": decision_sha,
                    "head_decision_v2_sha256": decision_sha,
                },
            },
            "timing": _copy(admitted.timing),
            "selection": _copy(admitted.selection),
            "head_observation": body_sway_review_head_observation_v2(
                revision, decision_sha,
            ),
            "compiler": compiler_profile_v2(),
            "claims": admission_claims_v2(),
            "status": "admitted_for_safety_analysis",
            "release_gate": admission_release_gate_v2(),
        }
        require_body_sway_review_admission_v2(document)
        return BodySwayReviewAdmissionV2(_canonical(document))
    except BodySwayReviewAdmissionV2Error:
        raise
    except _FAILURES as exc:
        raise BodySwayReviewAdmissionV2Error(
            f"Body-sway review admission v2 compilation failed: {exc}"
        ) from exc


def _copy(value: Any) -> Any:
    return json.loads(_canonical(value))


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )


_FAILURES = (
    AttributeError, BodySwayReviewAdmissionInputV2Error,
    BodySwayReviewAdmissionV2ValidationError, KeyError, OverflowError,
    RecursionError, TypeError, UnicodeError, ValueError,
)


__all__ = [
    "BodySwayReviewAdmissionV2", "BodySwayReviewAdmissionV2Error",
    "compile_body_sway_review_admission_v2",
]
