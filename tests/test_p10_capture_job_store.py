"""Contract, CAS, persistence, and restart tests for P10 capture jobs."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.p10_capture_job_contract import (  # noqa: E402
    JOB_ID_DOMAIN,
    P10CaptureJobContractError,
    P10CaptureJobEvent,
    P10CaptureJobRequest,
)
from autospine_workbench.p10_capture_job_store import (  # noqa: E402
    JOB_NAMESPACE,
    P10CaptureJobConflict,
    P10CaptureJobStore,
    P10CaptureJobStoreError,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402


SHA = {name: character * 64 for name, character in {
    "package": "1", "p10_candidate": "2", "p10_decision": "3",
    "frame_candidate": "4", "frame_decision": "5",
    "preview": "6", "execution": "7", "artifact": "8",
}.items()}


def request_payload(client="browser-request-1"):
    return {
        "package_id": SHA["package"],
        "client_request_id": client,
        "expected_p10_1": {
            "candidate_sha256": SHA["p10_candidate"],
            "decision_sha256": SHA["p10_decision"],
            "revision": 3,
        },
        "expected_framing": {
            "candidate_sha256": SHA["frame_candidate"],
            "decision_sha256": SHA["frame_decision"],
            "revision": 2,
        },
        "explicit_runtime_license_confirmation": True,
        "explicit_run_confirmation": True,
    }


ADDRESSES = {
    "project": "fixture-project",
    "preview": SHA["preview"],
    "execution_bundle": SHA["execution"],
    "artifact": SHA["artifact"],
}


class P10CaptureJobStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.state = Path(self.temporary.name)
        self.store = P10CaptureJobStore(self.state)

    def tearDown(self):
        self.temporary.cleanup()

    def test_request_is_strict_domain_separated_and_order_stable(self):
        payload = request_payload()
        first = P10CaptureJobRequest.from_payload(payload)
        reverse = dict(reversed(tuple(payload.items())))
        second = P10CaptureJobRequest.from_payload(reverse)
        self.assertEqual(first.canonical_bytes, second.canonical_bytes)
        self.assertEqual(first.job_id, second.job_id)
        self.assertNotEqual(canonical_sha256(first.document), first.job_id)
        self.assertEqual(
            first.job_id,
            canonical_sha256({"domain": JOB_ID_DOMAIN, "request": first.document}),
        )
        for mutate in (
            lambda row: row.update(extra=True),
            lambda row: row.update(explicit_run_confirmation=False),
            lambda row: row.update(explicit_runtime_license_confirmation=1),
            lambda row: row.update(client_request_id="../private/path"),
        ):
            invalid = request_payload()
            mutate(invalid)
            with self.subTest(invalid=invalid), self.assertRaises(
                P10CaptureJobContractError,
            ):
                P10CaptureJobRequest.from_payload(invalid)

    def test_create_is_idempotent_and_persists_exact_inventory(self):
        first = self.store.create(request_payload())
        second = self.store.create(request_payload())
        self.assertEqual(first, second)
        self.assertEqual("queued", first.status)
        self.assertEqual(1, len(first.events))
        directory = (
            self.state / "jobs" / JOB_NAMESPACE / first.job_id
        )
        self.assertEqual(
            {"request.json", "events"},
            {child.name for child in directory.iterdir()},
        )
        self.assertEqual(
            ["000001.json"],
            [child.name for child in (directory / "events").iterdir()],
        )
        self.assertEqual(
            first.request.canonical_bytes,
            (directory / "request.json").read_bytes(),
        )
        public = first.public_document()
        self.assertNotIn(str(self.state), repr(public))
        self.assertNotIn("path", repr(public).lower())
        self.assertTrue(
            public["request"]["explicit_runtime_license_confirmation"]
        )

    def test_full_lifecycle_is_hash_chained_and_completed_is_addressed(self):
        snapshot = self.store.create(request_payload())
        snapshot = self._append(snapshot, "exact_replay")
        snapshot = self._append(snapshot, "preview_compiled")
        snapshot = self._append(snapshot, "runtime_verified")
        for current in range(3):
            snapshot = self._append(
                snapshot, "capturing", current=current, total=2,
            )
        snapshot = self._append(snapshot, "sealing")
        snapshot = self._append(snapshot, "completed", addresses=ADDRESSES)
        self.assertEqual("completed", snapshot.status)
        self.assertEqual(ADDRESSES, snapshot.public_document()["addresses"])
        self.assertTrue(snapshot.public_document()["terminal"])
        previous = None
        for sequence, event in enumerate(snapshot.events, start=1):
            row = event.document
            self.assertEqual(sequence, row["sequence"])
            self.assertEqual(previous, row["previous_event_sha"])
            previous = event.event_sha
        with self.assertRaises(P10CaptureJobContractError):
            self._append(snapshot, "exact_replay")

    def test_compare_and_swap_exact_retry_and_progress_rules(self):
        queued = self.store.create(request_payload())
        replaying = self._append(queued, "exact_replay")
        exact_retry = self.store.append_event(
            queued.job_id, "exact_replay",
            expected_previous_event_sha=queued.head_event_sha,
        )
        self.assertEqual(replaying, exact_retry)
        with self.assertRaises(P10CaptureJobConflict) as stale:
            self.store.append_event(
                queued.job_id, "preview_compiled",
                expected_previous_event_sha=queued.head_event_sha,
            )
        self.assertEqual(replaying.head_event_sha, stale.exception.current_event_sha)
        other = self.store.create(request_payload("bad-transition"))
        with self.assertRaises(P10CaptureJobContractError):
            self._append(other, "capturing", current=0, total=2)
        other = self._append(other, "exact_replay")
        other = self._append(other, "preview_compiled")
        other = self._append(other, "runtime_verified")
        other = self._append(other, "capturing", current=1, total=2)
        with self.assertRaises(P10CaptureJobContractError):
            self._append(other, "capturing", current=0, total=2)
        with self.assertRaises(P10CaptureJobContractError):
            self._append(other, "sealing")

    def test_completed_and_failure_payloads_are_status_specific(self):
        job = P10CaptureJobRequest.from_payload(request_payload()).job_id
        with self.assertRaises(P10CaptureJobContractError):
            P10CaptureJobEvent.build(job, 2, "completed", "a" * 64)
        with self.assertRaises(P10CaptureJobContractError):
            P10CaptureJobEvent.build(
                job, 2, "queued", "a" * 64, addresses=ADDRESSES,
            )
        with self.assertRaises(P10CaptureJobContractError):
            P10CaptureJobEvent.build(
                job, 2, "failed_retryable", "a" * 64,
                failure_code=r"C:\private\error.log",
            )

    def test_public_failure_diagnostic_is_derived_without_rewriting_events(self):
        snapshot = self.store.create(request_payload("diagnostic"))
        snapshot = self._append(snapshot, "exact_replay")
        snapshot = self._append(snapshot, "preview_compiled")
        snapshot = self._append(snapshot, "runtime_verified")
        snapshot = self._append(snapshot, "capturing", current=0, total=43)
        snapshot = self._append(snapshot, "capturing", current=13, total=43)
        before = tuple(event.canonical_bytes for event in snapshot.events)
        snapshot = self._append(
            snapshot, "failed_retryable", failure_code="runtime_capture_failed",
        )
        diagnostic = snapshot.public_document()["failure_diagnostic"]
        self.assertEqual("case_capture", diagnostic["stage"])
        self.assertEqual("runtime_execution", diagnostic["category"])
        self.assertEqual(13, diagnostic["completed_case_count"])
        self.assertEqual(14, diagnostic["next_incomplete_case_ordinal"])
        self.assertEqual(before, tuple(
            event.canonical_bytes for event in snapshot.events[:-1]
        ))

    def test_tamper_and_non_contiguous_inventory_fail_closed(self):
        snapshot = self.store.create(request_payload())
        events = self._events(snapshot)
        raw = (events / "000001.json").read_text(encoding="utf-8")
        (events / "000001.json").write_text(raw + "\n", encoding="utf-8")
        with self.assertRaises(P10CaptureJobStoreError):
            self.store.load(snapshot.job_id)

        second = self.store.create(request_payload("gap"))
        event = self._events(second) / "000001.json"
        event.rename(event.with_name("000002.json"))
        with self.assertRaises(P10CaptureJobStoreError):
            self.store.load(second.job_id)

    def test_recovery_only_interrupts_active_preexisting_jobs_once(self):
        active = self.store.create(request_payload("active"))
        active = self._append(active, "exact_replay")
        retryable = self.store.create(request_payload("retryable"))
        retryable = self._append(
            retryable, "failed_retryable", failure_code="browser_timeout",
        )
        terminal = self.store.create(request_payload("terminal"))
        terminal = self._append(
            terminal, "failed_terminal", failure_code="identity_mismatch",
        )
        self.assertEqual((active.job_id,), self.store.recover_interrupted_jobs())
        recovered = self.store.load(active.job_id)
        self.assertEqual("interrupted_retryable", recovered.status)
        self.assertEqual("process_restart", recovered.public_document()["failure_code"])
        self.assertEqual("failed_retryable", self.store.load(retryable.job_id).status)
        self.assertEqual("failed_terminal", self.store.load(terminal.job_id).status)
        self.assertEqual((), self.store.recover_interrupted_jobs())

    def test_recovery_settles_a_request_published_before_queued_event(self):
        partial = self.store.create(request_payload("partial-publication"))
        (self._events(partial) / "000001.json").unlink()
        self.assertEqual((), self.store.load(partial.job_id).events)
        self.assertEqual((partial.job_id,), self.store.recover_interrupted_jobs())
        recovered = self.store.load(partial.job_id)
        self.assertEqual(
            ["queued", "interrupted_retryable"],
            [event.document["status"] for event in recovered.events],
        )

    def _append(self, snapshot, status, **payload):
        return self.store.append_event(
            snapshot.job_id, status,
            expected_previous_event_sha=snapshot.head_event_sha,
            **payload,
        )

    def _events(self, snapshot):
        return self.state / "jobs" / JOB_NAMESPACE / snapshot.job_id / "events"


if __name__ == "__main__":
    unittest.main()
