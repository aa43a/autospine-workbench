"""Pure file-input service for P10 idle-behavior decisions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .idle_behavior_candidate_validation import (
    MAX_DOCUMENT_BYTES as MAX_CANDIDATE_BYTES,
    IdleBehaviorCandidateValidationError,
    idle_behavior_candidates_sha256,
)
from .idle_behavior_decision import (
    IdleBehaviorDecisionError,
    build_idle_behavior_decision,
)
from .idle_behavior_decision_validation import (
    MAX_DOCUMENT_BYTES as MAX_REVIEW_INPUT_BYTES,
)
from .safe_input_files import (
    SafeInputFileError,
    read_real_file,
    strict_json_object,
)


class P10DecisionCommandError(RuntimeError):
    """Raised when exact review files cannot form a decision document."""


@dataclass(frozen=True, slots=True)
class P10DecisionCommandResult:
    """Canonical decision and exact identities of both input documents."""

    input_paths: tuple[Path, Path]
    idle_behavior_candidates_sha256: str
    idle_behavior_decision_sha256: str
    document: dict[str, Any]


def compile_idle_behavior_decision_command(
    candidates_path: Path,
    review_input_path: Path,
) -> P10DecisionCommandResult:
    """Read two bounded strict JSON files and invoke the pure builder."""

    try:
        candidate_path = Path(candidates_path)
        review_path = Path(review_input_path)
        candidates = strict_json_object(
            read_real_file(
                candidate_path,
                MAX_CANDIDATE_BYTES,
                "Idle behavior candidates",
            ),
            "Idle behavior candidates",
        )
        review_input = strict_json_object(
            read_real_file(
                review_path,
                MAX_REVIEW_INPUT_BYTES,
                "Idle behavior review input",
            ),
            "Idle behavior review input",
        )
        if set(review_input) != {"review", "decisions"}:
            raise P10DecisionCommandError(
                "Idle behavior review input fields are unsupported"
            )
        compiled = build_idle_behavior_decision(
            candidates,
            review=review_input["review"],
            decisions=review_input["decisions"],
        )
        return P10DecisionCommandResult(
            input_paths=(candidate_path, review_path),
            idle_behavior_candidates_sha256=(
                idle_behavior_candidates_sha256(candidates)
            ),
            idle_behavior_decision_sha256=compiled.sha256,
            document=compiled.document,
        )
    except P10DecisionCommandError:
        raise
    except (
        IdleBehaviorCandidateValidationError,
        IdleBehaviorDecisionError,
        KeyError,
        OSError,
        OverflowError,
        RecursionError,
        SafeInputFileError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as exc:
        raise P10DecisionCommandError(
            f"Idle behavior decision command failed: {exc}"
        ) from exc
