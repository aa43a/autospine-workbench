"""Small deterministic fixtures for P10.4b v2 job tests."""

from __future__ import annotations

from autospine_workbench.p10_capture_job_contract import (
    P10CaptureJobEvent,
    P10CaptureJobRequest,
)
from autospine_workbench.p10_capture_job_store import P10CaptureJobSnapshot
from autospine_workbench.p10_completed_job_snapshot import (
    verified_completed_p10_capture_job,
)


SHA = {str(index): f"{index:x}" * 64 for index in range(1, 10)}


def completed_capture_job():
    request = P10CaptureJobRequest.from_payload({
        "package_id": SHA["1"],
        "client_request_id": "safety-analysis-test",
        "expected_p10_1": {
            "candidate_sha256": SHA["2"],
            "decision_sha256": SHA["3"], "revision": 1,
        },
        "expected_framing": {
            "candidate_sha256": SHA["4"],
            "decision_sha256": SHA["5"], "revision": 1,
        },
        "explicit_runtime_license_confirmation": True,
        "explicit_run_confirmation": True,
    })
    rows = (
        ("queued", {}), ("exact_replay", {}),
        ("preview_compiled", {}), ("runtime_verified", {}),
        ("capturing", {"current": 1, "total": 1}),
        ("sealing", {}),
        ("completed", {"addresses": {
            "project": "fixture-project", "preview": SHA["6"],
            "execution_bundle": SHA["7"], "artifact": SHA["8"],
        }}),
    )
    events = []
    previous = None
    for sequence, (status, payload) in enumerate(rows, 1):
        event = P10CaptureJobEvent.build(
            request.job_id, sequence, status,
            previous.event_sha if previous else None, **payload,
        )
        events.append(event)
        previous = event
    public = P10CaptureJobSnapshot(
        request, tuple(events),
    ).public_document()
    return verified_completed_p10_capture_job(public, request.job_id)


__all__ = ["SHA", "completed_capture_job"]
