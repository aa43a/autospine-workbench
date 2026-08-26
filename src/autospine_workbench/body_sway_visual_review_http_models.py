"""Path-free JSON projections for the P10.3c HTTP adapter."""

from __future__ import annotations

from typing import Any


def candidate_response(prepared) -> dict[str, Any]:
    return {
        "candidate_sha256": prepared.candidate_sha256,
        "candidate": prepared.candidate_document,
    }


def history_response(prepared) -> dict[str, Any]:
    history = prepared.history
    return {
        "candidate_sha256": prepared.candidate_sha256,
        "current_revision": history.current_revision,
        "head_decision_sha256": history.head_decision_sha256,
        "items": [
            {
                "revision": row.revision,
                "decision_sha256": row.decision_sha256,
                "status": row.status,
            }
            for row in history.rows
        ],
    }


def exact_decision_response(exact) -> dict[str, Any]:
    return {
        "candidate_sha256": exact.candidate_sha256,
        "decision_sha256": exact.decision_sha256,
        "decision": exact.decision_document,
    }


def submitted_response(result) -> dict[str, Any]:
    return {
        "candidate_sha256": result.candidate_sha256,
        "decision_sha256": result.decision_sha256,
        "revision": result.revision,
        "status": result.status,
        "release_gate": {
            "status": result.release_gate_status,
            "reason_codes": list(result.release_gate_reason_codes),
        },
        "summary": {
            "case_count": result.case_count,
            "approve_count": result.approve_count,
            "reject_count": result.reject_count,
            "unobservable_count": result.unobservable_count,
        },
        "reused": result.reused,
    }
