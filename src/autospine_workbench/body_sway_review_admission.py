"""Pure canonical compiler for BodySwayReviewAdmission v1."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .body_sway_review_admission_inputs import (
    BodySwayReviewAdmissionInput,
    BodySwayReviewAdmissionInputError,
    require_body_sway_review_admission_input,
)
from .body_sway_review_admission_profile import (
    admission_claims,
    admission_release_gate,
    body_sway_review_head_observation,
    compiler_profile,
)
from .body_sway_review_admission_validation import (
    FORMAT,
    FORMAT_VERSION,
    BodySwayReviewAdmissionValidationError,
    require_body_sway_review_admission,
)


class BodySwayReviewAdmissionError(ValueError):
    """Raised when exact reviewed evidence cannot form an admission."""


@dataclass(frozen=True, slots=True)
class BodySwayReviewAdmission:
    """Frozen path-free admission bytes and their canonical identity."""

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


def compile_body_sway_review_admission(
    inputs: BodySwayReviewAdmissionInput,
) -> BodySwayReviewAdmission:
    """Admit only the approved head observed in two matching snapshots."""

    try:
        admitted = require_body_sway_review_admission_input(inputs)
        address = admitted.address
        preview = admitted.preview_document
        revision = admitted.visual_revision
        decision_sha = admitted.visual_decision_sha256
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "project_id": admitted.project_id,
            "clip_id": admitted.clip_id,
            "source": {
                "p10_chain": _copy(admitted.source),
                "capture": {
                    "project_id": address.project_id,
                    "temporary_preview_sha256":
                        address.temporary_preview_sha256,
                    "runtime_capture_manifest_sha256":
                        admitted.runtime_capture_manifest_sha256,
                    "runtime_capture_bundle_sha256":
                        address.runtime_capture_bundle_sha256,
                    "capture_artifact_set_sha256":
                        address.capture_artifact_set_sha256,
                    "preview_artifact_set_sha256": preview["artifacts"][
                        "artifact_set_sha256"
                    ],
                },
                "visual_review": {
                    "candidate_sha256": admitted.visual_candidate_sha256,
                    "revision": revision,
                    "decision_sha256": decision_sha,
                    "head_decision_sha256": decision_sha,
                },
            },
            "timing": _copy(admitted.timing),
            "selection": _copy(admitted.selection),
            "head_observation": body_sway_review_head_observation(
                revision, decision_sha
            ),
            "compiler": compiler_profile(),
            "claims": admission_claims(),
            "status": "admitted_for_safety_analysis",
            "release_gate": admission_release_gate(),
        }
        require_body_sway_review_admission(document)
        return BodySwayReviewAdmission(_canonical(document))
    except BodySwayReviewAdmissionError:
        raise
    except (
        BodySwayReviewAdmissionInputError,
        BodySwayReviewAdmissionValidationError,
        AttributeError, KeyError, OverflowError, RecursionError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayReviewAdmissionError(
            f"Body-sway review admission compilation failed: {exc}"
        ) from exc


def _copy(value: Any) -> Any:
    return json.loads(_canonical(value))


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
