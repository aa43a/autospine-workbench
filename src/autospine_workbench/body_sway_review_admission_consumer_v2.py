"""Current-head consumer boundary for historical P10.4a v2 documents."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Mapping

from .body_sway_review_admission_validation_v2 import (
    BodySwayReviewAdmissionV2ValidationError,
    require_body_sway_review_admission_v2,
)
from .p10_review_admission_v2_commands import (
    P10ReviewAdmissionV2CommandError,
    P10ReviewAdmissionV2CommandResult,
    compile_body_sway_review_admission_v2_for_job,
)
from .project_store import ProjectStore


class BodySwayReviewAdmissionV2ConsumerError(RuntimeError):
    """Raised when a detached admission is no longer the exact current head."""


@dataclass(frozen=True, slots=True)
class CurrentBodySwayReviewAdmissionV2:
    """Process-local proof retaining reloaded exact inputs privately."""

    admission_sha256: str
    _result: P10ReviewAdmissionV2CommandResult = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return self._result.document

    @property
    def job_id(self) -> str:
        return self._result.job_id


def require_current_body_sway_review_admission_v2(
    job_reader: Any,
    store: ProjectStore,
    document: Mapping[str, Any],
) -> CurrentBodySwayReviewAdmissionV2:
    """Recompile current authority and require byte-identical admission output."""

    try:
        require_body_sway_review_admission_v2(document)
        expected = _canonical(document)
        source = document["source"]
        job = source["job"]
        visual = source["visual_review"]
        result = compile_body_sway_review_admission_v2_for_job(
            job_reader, store, job["job_id"],
            expected_candidate_sha256=visual["candidate_v2_sha256"],
            expected_visual_revision=visual["revision"],
            expected_decision_sha256=visual["decision_v2_sha256"],
        )
        if _canonical(result.document) != expected:
            raise BodySwayReviewAdmissionV2ConsumerError(
                "Body-sway review admission v2 is no longer current"
            )
        return CurrentBodySwayReviewAdmissionV2(
            result.admission_sha256, result,
        )
    except BodySwayReviewAdmissionV2ConsumerError:
        raise
    except (
        BodySwayReviewAdmissionV2ValidationError, KeyError,
        OverflowError, P10ReviewAdmissionV2CommandError, RecursionError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayReviewAdmissionV2ConsumerError(
            "Current body-sway review admission v2 verification failed"
        ) from exc


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )


__all__ = [
    "BodySwayReviewAdmissionV2ConsumerError",
    "CurrentBodySwayReviewAdmissionV2",
    "require_current_body_sway_review_admission_v2",
]
