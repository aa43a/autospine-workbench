"""Small JSON-file helpers for the P10 decision command boundary."""

from __future__ import annotations

import json
from pathlib import Path

from tests.idle_behavior_decision_helpers import (
    adjust_decision,
    completed_review,
)
from tests.test_idle_behavior_candidate_validation import valid_candidates


def candidate_document() -> dict:
    return valid_candidates()


def review_input(candidates=None) -> dict:
    selected = candidate_document() if candidates is None else candidates
    return {
        "review": completed_review(),
        "decisions": [adjust_decision(selected)],
    }


def write_json(path: Path, value) -> Path:
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    return path
