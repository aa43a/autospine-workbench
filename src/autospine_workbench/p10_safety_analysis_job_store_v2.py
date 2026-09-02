"""Append-only local store for P10.4b v2 asynchronous runs."""

from __future__ import annotations

from pathlib import Path

from .p10_safety_analysis_job_files_v2 import (
    P10SafetyAnalysisJobFilesV2Error, event_inventory,
    exact_directory, normalized_state_root, publish_once, read_json,
    read_latest_index, replace_latest_index, require_run_id,
    run_directory, run_ids,
)
from .p10_safety_analysis_job_contract_v2 import (
    ACTIVE,
    P10SafetyAnalysisRunEventV2, P10SafetyAnalysisRunRequestV2,
    require_transition,
)
from .p10_safety_analysis_job_snapshot_v2 import (
    P10SafetyAnalysisJobSnapshotV2,
)
from .p10_safety_analysis_attempt_index_v2 import (
    require_attempt_chain, require_latest_index,
    valid_attempt_predecessor,
)
from .p10_safety_analysis_result_store_v2 import (
    P10SafetyAnalysisResultStoreV2,
    P10SafetyAnalysisResultStoreV2Error,
)


P10SafetyAnalysisJobStoreV2Error = P10SafetyAnalysisJobFilesV2Error


class P10SafetyAnalysisJobConflictV2(P10SafetyAnalysisJobStoreV2Error):
    pass


class P10SafetyAnalysisJobStoreV2:
    def __init__(self, state_root: Path) -> None:
        try:
            self.state_root = normalized_state_root(state_root)
        except P10SafetyAnalysisJobFilesV2Error as exc:
            raise P10SafetyAnalysisJobStoreV2Error(
                "Safety analysis state root is invalid"
            ) from exc
        self._results = P10SafetyAnalysisResultStoreV2(self.state_root)

    def create(self, request: P10SafetyAnalysisRunRequestV2):
        if type(request) is not P10SafetyAnalysisRunRequestV2:
            raise P10SafetyAnalysisJobStoreV2Error(
                "Safety analysis request type is invalid"
            )
        existing = self.latest_for_job(request.document["job_id"])
        if existing is not None and existing.run_id == request.run_id:
            if not existing.events:
                existing = self.append(
                    request.run_id, "queued", "queued",
                    expected_previous=None, current=0, total=1,
                )
                self._write_latest(existing)
            return existing
        if not valid_attempt_predecessor(existing, request):
            raise P10SafetyAnalysisJobConflictV2(
                "Safety analysis attempt predecessor is stale"
            )
        directory = self._run_directory(request.run_id, create=True)
        publish_once(directory / "request.json", request.canonical_bytes)
        exact_directory(directory, "events", create=True)
        snapshot = self.load(request.run_id)
        if snapshot.request.canonical_bytes != request.canonical_bytes:
            raise P10SafetyAnalysisJobConflictV2(
                "Safety analysis run id is already bound differently"
            )
        if not snapshot.events:
            snapshot = self.append(
                request.run_id, "queued", "queued",
                expected_previous=None, current=0, total=1,
            )
        self._write_latest(snapshot)
        return snapshot

    def latest_for_job(self, job_id: str):
        """Return the latest exact attempt for a job, rejecting forks/gaps."""

        index = read_latest_index(self.state_root, job_id)
        if index is None:
            return None
        require_latest_index(index, job_id)
        snapshot = self.load(index["run_id"])
        request = snapshot.request.document
        if request["job_id"] != job_id \
                or request["attempt"] != index["attempt"] \
                or request["previous_run_id"] != index["previous_run_id"]:
            raise P10SafetyAnalysisJobStoreV2Error(
                "Safety analysis latest index is cross-wired"
            )
        return snapshot

    def load(self, run_id: str):
        require_run_id(run_id)
        directory = self._run_directory(run_id, create=False)
        request = P10SafetyAnalysisRunRequestV2.from_document(
            read_json(directory / "request.json", 128 * 1024)
        )
        if request.run_id != run_id:
            raise P10SafetyAnalysisJobStoreV2Error(
                "Safety analysis request address differs"
            )
        events_dir = exact_directory(directory, "events", create=False)
        events = []
        for sequence, path in event_inventory(events_dir):
            event = P10SafetyAnalysisRunEventV2.from_document(
                read_json(path, 128 * 1024)
            )
            if event.document["sequence"] != sequence:
                raise P10SafetyAnalysisJobStoreV2Error(
                    "Safety analysis event sequence differs"
                )
            require_transition(events[-1] if events else None, event)
            events.append(event)
        return P10SafetyAnalysisJobSnapshotV2(request, tuple(events))

    def append(
        self, run_id, status, stage, *, expected_previous,
        current=0, total=1, failure_code=None, result=None,
    ):
        snapshot = self.load(run_id)
        if snapshot.head_event_sha256 != expected_previous:
            raise P10SafetyAnalysisJobConflictV2(
                "Safety analysis event predecessor is stale"
            )
        event = P10SafetyAnalysisRunEventV2.build(
            run_id, len(snapshot.events) + 1, expected_previous,
            status, stage, current=current, total=total,
            failure_code=failure_code, result=result,
        )
        require_transition(snapshot.events[-1] if snapshot.events else None,
                           event)
        directory = self._run_directory(run_id, create=False)
        publish_once(
            exact_directory(directory, "events", create=False)
            / f"{len(snapshot.events) + 1:06d}.json",
            event.canonical_bytes,
        )
        current_snapshot = self.load(run_id)
        if current_snapshot.head_event_sha256 != event.event_sha256:
            raise P10SafetyAnalysisJobStoreV2Error(
                "Safety analysis event failed exact readback"
            )
        return current_snapshot

    def publish_result(
        self, run_id, amplitude, continuous, *, admission_sha256,
        visual_candidate_sha256, visual_revision, visual_decision_sha256,
    ):
        snapshot = self.load(run_id)
        if snapshot.status not in ACTIVE:
            raise P10SafetyAnalysisJobStoreV2Error(
                "Safety analysis result cannot be published now"
            )
        try:
            return self._results.publish(
                run_id, amplitude, continuous,
                admission_sha256=admission_sha256,
                visual_candidate_sha256=visual_candidate_sha256,
                visual_revision=visual_revision,
                visual_decision_sha256=visual_decision_sha256,
            )
        except P10SafetyAnalysisResultStoreV2Error as exc:
            raise P10SafetyAnalysisJobStoreV2Error(str(exc)) from exc

    def verify_staged_result(self, run_id, result):
        """Verify worker-published bytes before a completed event exists."""

        snapshot = self.load(run_id)
        if snapshot.status not in ACTIVE:
            raise P10SafetyAnalysisJobStoreV2Error(
                "Safety analysis staged result cannot be verified now"
            )
        try:
            return self._results.read_and_validate(
                run_id, snapshot.request.document, result,
            )
        except P10SafetyAnalysisResultStoreV2Error as exc:
            raise P10SafetyAnalysisJobStoreV2Error(str(exc)) from exc

    def read_result(self, run_id):
        snapshot = self.load(run_id)
        head = snapshot.events[-1].document if snapshot.events else {}
        if snapshot.status != "completed" or not isinstance(
            head.get("result"), dict
        ):
            raise P10SafetyAnalysisJobStoreV2Error(
                "Safety analysis result is not complete"
            )
        try:
            return self._results.read_and_validate(
                run_id, snapshot.request.document, head["result"],
            )
        except P10SafetyAnalysisResultStoreV2Error as exc:
            raise P10SafetyAnalysisJobStoreV2Error(
                "Safety analysis result binding differs"
            ) from exc

    def recover_interrupted(self):
        recovered = []
        snapshots = [self.load(run_id) for run_id in self._run_ids()]
        by_job = {}
        for snapshot in snapshots:
            by_job.setdefault(
                snapshot.request.document["job_id"], []
            ).append(snapshot)
        for job_id, attempts in by_job.items():
            attempts.sort(key=lambda row: row.request.document["attempt"])
            require_attempt_chain(attempts)
            snapshot = attempts[-1]
            if not snapshot.events:
                snapshot = self.append(
                    snapshot.run_id, "queued", "queued",
                    expected_previous=None, current=0, total=1,
                )
            if snapshot.status in ACTIVE:
                snapshot = self.append(
                    snapshot.run_id, "failed_retryable", "failed",
                    expected_previous=snapshot.head_event_sha256,
                    failure_code="process_restart",
                )
                recovered.append(snapshot.run_id)
            self._write_latest(snapshot)
        return tuple(recovered)

    def _run_directory(self, run_id, *, create):
        return run_directory(self.state_root, run_id, create=create)

    def _run_ids(self):
        return run_ids(self.state_root)

    def _write_latest(self, snapshot) -> None:
        request = snapshot.request.document
        replace_latest_index(self.state_root, request["job_id"], {
            "format": "autospine-p10-safety-analysis-latest-v2",
            "format_version": 2, "job_id": request["job_id"],
            "attempt": request["attempt"], "run_id": snapshot.run_id,
            "previous_run_id": request["previous_run_id"],
        })
__all__ = [
    "P10SafetyAnalysisJobConflictV2", "P10SafetyAnalysisJobSnapshotV2",
    "P10SafetyAnalysisJobStoreV2", "P10SafetyAnalysisJobStoreV2Error",
]
