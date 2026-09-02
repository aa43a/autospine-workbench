"""Persistence and recovery tests for P10.7b v2 authorized jobs."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.p10_spine42_v3_runtime_job_contract_v2 import (
    P10Spine42V3RuntimeJobRequestV2,
)
from autospine_workbench.p10_spine42_v3_runtime_job_store_v2 import (
    AUTHORIZATION_NAMESPACE,
    JOB_NAMESPACE,
    P10Spine42V3RuntimeJobConflictV2,
    P10Spine42V3RuntimeJobStoreV2,
    P10Spine42V3RuntimeJobStoreV2Error,
)
from tests.test_p10_spine42_v3_runtime_job_contract_v2 import (
    _address, _browser, _payload, _runtime, _sha,
)


def _request(*, runtime=None, browser=None, **changes):
    return P10Spine42V3RuntimeJobRequestV2.expand(
        _payload(**changes), project_id="sample", clip_id="idle",
        skeleton_json_sha256=_sha("3"),
        spine42_v3_bundle_sha256=_sha("4"),
        runtime=runtime or _runtime(), browser=browser or _browser(),
    )


def _append(store, row, stage, *, current=0, total=1, address=None):
    return store.append_event(
        row.job_id, "running", stage,
        expected_previous_event_sha256=row.head_event_sha256,
        current=current, total=total, capture_address=address,
    )


def _reach(store, request, stop):
    row = store.create(request)
    for stage in ("exact_source_readback", "runtime_reverified"):
        row = _append(store, row, stage)
        if stage == stop:
            return row
    row = _append(store, row, "capturing", current=0, total=1)
    if stop == "capturing":
        return row
    row = _append(store, row, "capturing", current=1, total=1)
    row = _append(store, row, "evidence_compiling")
    if stop == "evidence_compiling":
        return row
    row = _append(store, row, "publishing", address=_address())
    if stop == "publishing":
        return row
    return _append(store, row, "parent_exact_readback", address=_address())


class P10Spine42V3RuntimeJobStoreV2Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = P10Spine42V3RuntimeJobStoreV2(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def test_duplicate_create_is_same_queued_journal_without_authority(self):
        request = _request()
        first = self.store.create(request)
        duplicate = self.store.create(request)
        self.assertEqual(first.job_id, duplicate.job_id)
        self.assertEqual("queued", duplicate.status)
        self.assertEqual(1, len(duplicate.events))
        public = duplicate.public_document()
        self.assertFalse(public["runner_execution_authorized"])
        self.assertNotIn("path", repr(public).lower())
        self.assertNotIn("private", repr(public).lower())
        committed = self.root / "jobs" / JOB_NAMESPACE / request.job_id
        self.assertEqual({"events", "request.json"}, {p.name for p in committed.iterdir()})
        self.assertEqual(["000001.json"], [p.name for p in (committed / "events").iterdir()])

    def test_same_authorization_is_globally_bound_to_one_expanded_request(self):
        first = self.store.create(_request())
        self.assertEqual("queued", first.status)
        with self.assertRaises(P10Spine42V3RuntimeJobConflictV2):
            self.store.create(_request(candidate_id=_sha("6")))
        authorization_root = (
            self.root / "jobs" / AUTHORIZATION_NAMESPACE
        )
        self.assertEqual(1, len(list(authorization_root.iterdir())))

    def test_retry_requires_retryable_predecessor_and_new_authorization(self):
        first = _reach(self.store, _request(), "capturing")
        first = self.store.append_event(
            first.job_id, "failed_retryable", "capturing",
            expected_previous_event_sha256=first.head_event_sha256,
            failure_code="browser_failed", resume_mode="new_authorization",
        )
        retry = _request(
            authorization_id="auth-00000002",
            retry_of_job_id=first.job_id,
        )
        second = self.store.create(retry)
        self.assertNotEqual(first.job_id, second.job_id)
        self.assertEqual(first.job_id,
                         second.request.document["retry_of_job_id"])
        with self.assertRaises(P10Spine42V3RuntimeJobConflictV2):
            self.store.create(_request(
                authorization_id="auth-00000003",
                retry_of_job_id=first.job_id,
            ))
        same_auth = _request(retry_of_job_id=first.job_id)
        with self.assertRaises(P10Spine42V3RuntimeJobConflictV2):
            self.store.create(same_auth)

    def test_retry_accepts_newly_reverified_runtime_and_browser_identity(self):
        first = _reach(self.store, _request(), "capturing")
        first = self.store.append_event(
            first.job_id, "failed_retryable", "capturing",
            expected_previous_event_sha256=first.head_event_sha256,
            failure_code="browser_updated", resume_mode="new_authorization")
        changed_runtime = replace(
            _runtime(), javascript_sha256=_sha("8"))
        changed_browser = replace(
            _browser(), reported_version="Chrome 141.0.0.0",
            version_output_sha256=_sha("8"), executable_sha256=_sha("9"))
        retry = _request(
            runtime=changed_runtime, browser=changed_browser,
            authorization_id="auth-00000002", retry_of_job_id=first.job_id)
        self.assertEqual("queued", self.store.create(retry).status)

    def test_child_load_requires_its_exact_predecessor_history(self):
        first = _reach(self.store, _request(), "capturing")
        first = self.store.append_event(
            first.job_id, "failed_retryable", "capturing",
            expected_previous_event_sha256=first.head_event_sha256,
            failure_code="browser_failed", resume_mode="new_authorization")
        child = self.store.create(_request(
            authorization_id="auth-00000002",
            retry_of_job_id=first.job_id))
        predecessor = self.root / "jobs" / JOB_NAMESPACE / first.job_id
        predecessor.rename(self.root / "removed-predecessor")
        with self.assertRaises(P10Spine42V3RuntimeJobStoreV2Error):
            self.store.load(child.job_id)

    def test_recovery_never_reexecutes_and_classifies_resume_mode(self):
        capture = _reach(self.store, _request(), "capturing")
        publishing = _reach(self.store, _request(
            candidate_id=_sha("6"), entry_sha256=_sha("7"),
            authorization_id="auth-00000002",
        ), "publishing")
        recovery = self.store.recover_interrupted()
        self.assertEqual((capture.job_id,), recovery.interrupted_job_ids)
        self.assertEqual(
            (publishing.job_id,), recovery.readback_required_job_ids)
        early = self.store.load(capture.job_id)
        late = self.store.load(publishing.job_id)
        self.assertEqual("interrupted_retryable", early.status)
        self.assertEqual("new_authorization", early.head["resume_mode"])
        self.assertEqual("running", late.status)
        self.assertEqual("publishing", late.head["stage"])
        late = _append(
            self.store, late, "parent_exact_readback", address=_address())
        late = self.store.append_event(
            late.job_id, "completed", "completed",
            expected_previous_event_sha256=late.head_event_sha256,
            current=1, total=1, result=_address(),
        )
        self.assertEqual("completed", late.status)
        settled = self.store.recover_interrupted()
        self.assertEqual((), settled.interrupted_job_ids)
        self.assertEqual((), settled.readback_required_job_ids)
        missing = _reach(self.store, _request(
            candidate_id=_sha("8"), entry_sha256=_sha("9"),
            authorization_id="auth-00000003"), "publishing")
        self.assertEqual((missing.job_id,), self.store.recover_interrupted(
        ).readback_required_job_ids)
        missing = self.store.append_event(
            missing.job_id, "failed_retryable", "publishing",
            expected_previous_event_sha256=missing.head_event_sha256,
            failure_code="capture_address_not_found",
            resume_mode="new_authorization", capture_address=_address())
        retry = _request(candidate_id=_sha("8"), entry_sha256=_sha("9"),
                         authorization_id="auth-00000004",
                         retry_of_job_id=missing.job_id)
        self.assertEqual("queued", self.store.create(retry).status)

    def test_completed_result_is_four_part_address_and_terminal(self):
        row = _reach(self.store, _request(), "parent_exact_readback")
        row = self.store.append_event(
            row.job_id, "completed", "completed",
            expected_previous_event_sha256=row.head_event_sha256,
            current=1, total=1, result=_address(),
        )
        self.assertEqual("completed", row.status)
        self.assertEqual(set(_address()), set(row.head["result"]))
        with self.assertRaises(P10Spine42V3RuntimeJobStoreV2Error):
            self.store.append_event(
                row.job_id, "running", "exact_source_readback",
                expected_previous_event_sha256=row.head_event_sha256,
            )

    def test_append_rejects_every_foreign_source_address_checkpoint(self):
        row = _reach(self.store, _request(), "evidence_compiling")
        variants = {
            "project_id": "other", "skeleton_json_sha256": _sha("8"),
            "spine42_v3_bundle_sha256": _sha("9"),
        }
        for field, value in variants.items():
            address = _address(); address[field] = value
            with self.subTest(field=field, stage="publishing"), \
                    self.assertRaises(P10Spine42V3RuntimeJobStoreV2Error):
                _append(self.store, row, "publishing", address=address)
        row = _append(self.store, row, "publishing", address=_address())
        for field, value in variants.items():
            address = _address(); address[field] = value
            with self.subTest(field=field, stage="late_failure"), \
                    self.assertRaises(P10Spine42V3RuntimeJobStoreV2Error):
                self.store.append_event(
                    row.job_id, "failed_retryable", "publishing",
                    expected_previous_event_sha256=row.head_event_sha256,
                    failure_code="readback_not_found",
                    resume_mode="new_authorization", capture_address=address)
        row = _append(self.store, row, "parent_exact_readback",
                      address=_address())
        for field, value in variants.items():
            address = _address(); address[field] = value
            with self.subTest(field=field, stage="completed"), \
                    self.assertRaises(P10Spine42V3RuntimeJobStoreV2Error):
                self.store.append_event(
                    row.job_id, "completed", "completed",
                    expected_previous_event_sha256=row.head_event_sha256,
                    current=1, total=1, result=address)

    def test_stale_event_cas_does_not_report_success_or_runner_authority(self):
        row = self.store.create(_request())
        head = row.head_event_sha256
        advanced = _append(self.store, row, "exact_source_readback")
        with self.assertRaises(P10Spine42V3RuntimeJobConflictV2):
            self.store.append_event(
                row.job_id, "running", "exact_source_readback",
                expected_previous_event_sha256=head,
            )
        self.assertFalse(advanced.public_document()[
            "runner_execution_authorized"
        ])

if __name__ == "__main__":
    unittest.main()
