"""Small fixtures for IdleBehaviorDecision v1 tests."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from tests.test_idle_behavior_candidate_validation import valid_candidates


def completed_review(revision: int = 1) -> dict[str, Any]:
    return {"method": "human", "status": "completed", "revision": revision}


def adjust_decision(candidates=None) -> dict[str, Any]:
    document = valid_candidates() if candidates is None else candidates
    candidate = next(
        row for row in document["features"]
        if row["availability"] == "candidate"
    )
    bone_ids = candidate["proposal"]["target_bone_ids"]
    amplitudes = [1.0, 2.0, 1.0, 0.5]
    phases = [0.0, 0.25, 0.5, 0.75]
    return {
        "candidate_id": candidate["candidate_id"],
        "feature_id": candidate["feature_id"],
        "action": "adjust",
        "reason_code": "human-parameterized",
        "payload": {
            "cycles": 2,
            "per_bone_amplitude_deg": [
                {"bone_id": bone_id, "value": value}
                for bone_id, value in zip(bone_ids, amplitudes, strict=True)
            ],
            "per_bone_phase_fraction": [
                {"bone_id": bone_id, "value": value}
                for bone_id, value in zip(bone_ids, phases, strict=True)
            ],
        },
        "probe_status": "pending_probe",
    }


def terminal_decision(action: str, candidates=None) -> dict[str, Any]:
    row = adjust_decision(candidates)
    row.update({
        "action": action,
        "reason_code": f"human-{action}",
        "payload": None,
        "probe_status": "not_applicable",
    })
    return row


def candidates_without_candidate() -> dict[str, Any]:
    document = deepcopy(valid_candidates())
    body_sway = document["features"][1]
    body_sway.update({
        "availability": "unobservable",
        "candidate_id": None,
        "proposal": None,
        "reason_codes": ["required-bone-evidence-missing"],
    })
    document["summary"].update({
        "candidate_count": 0,
        "unobservable_count": 3,
    })
    return document
