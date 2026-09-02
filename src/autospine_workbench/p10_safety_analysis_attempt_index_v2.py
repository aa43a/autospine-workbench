"""Attempt-chain and latest-index checks for P10.4b v2 jobs."""

from __future__ import annotations

from .p10_safety_analysis_job_files_v2 import (
    P10SafetyAnalysisJobFilesV2Error,
    require_run_id,
)
from .p10_safety_analysis_job_contract_v2 import TERMINAL


def valid_attempt_predecessor(previous, request) -> bool:
    row = request.document
    if previous is None:
        return row["attempt"] == 1 and row["previous_run_id"] is None
    return previous.status in TERMINAL \
        and row["attempt"] == previous.request.document["attempt"] + 1 \
        and row["previous_run_id"] == previous.run_id


def require_attempt_chain(attempts) -> None:
    previous = None
    for attempt, snapshot in enumerate(attempts, 1):
        request = snapshot.request.document
        if request["attempt"] != attempt \
                or request["previous_run_id"] \
                    != (previous.run_id if previous else None):
            raise P10SafetyAnalysisJobFilesV2Error(
                "Safety analysis attempt chain is not linear"
            )
        previous = snapshot


def require_latest_index(value, job_id) -> None:
    fields = {
        "format", "format_version", "job_id", "attempt", "run_id",
        "previous_run_id",
    }
    if not isinstance(value, dict) or set(value) != fields \
            or value.get("format") \
                != "autospine-p10-safety-analysis-latest-v2" \
            or value.get("format_version") != 2 \
            or value.get("job_id") != job_id \
            or type(value.get("attempt")) is not int \
            or not 1 <= value["attempt"] <= 10_000:
        raise P10SafetyAnalysisJobFilesV2Error(
            "Safety analysis latest index is invalid"
        )
    require_run_id(value.get("run_id"))
    if value["attempt"] == 1 and value.get("previous_run_id") is not None:
        raise P10SafetyAnalysisJobFilesV2Error(
            "Safety analysis latest predecessor is invalid"
        )
    if value["attempt"] > 1:
        require_run_id(value.get("previous_run_id"))


__all__ = [
    "require_attempt_chain", "require_latest_index",
    "valid_attempt_predecessor",
]
