"""Attempt, persistence, recovery, and large-file tests for P10.4b v2."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.p10_safety_analysis_job_contract_v2 import (  # noqa: E402
    P10SafetyAnalysisJobContractV2Error,
    P10SafetyAnalysisRunEventV2,
    P10SafetyAnalysisRunRequestV2,
)
from autospine_workbench.p10_safety_analysis_job_files_v2 import (  # noqa: E402
    LATEST_NAMESPACE,
    exact_directory,
    publish_once,
    read_json,
    run_directory,
)
from autospine_workbench.p10_safety_analysis_job_store_v2 import (  # noqa: E402
    P10SafetyAnalysisJobStoreV2,
)
from tests.p10_safety_analysis_job_v2_test_helpers import (  # noqa: E402
    completed_capture_job,
)


class P10SafetyAnalysisJobV2Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.state = Path(self.temporary.name)
        self.completed = completed_capture_job()
        self.first = P10SafetyAnalysisRunRequestV2.build(
            self.completed, attempt=1, previous_run_id=None,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_attempt_request_is_canonical_and_attempt_scoped(self):
        reverse = dict(reversed(tuple(self.first.document.items())))
        rebuilt = P10SafetyAnalysisRunRequestV2.from_document(reverse)
        self.assertEqual(self.first.run_id, rebuilt.run_id)
        second = P10SafetyAnalysisRunRequestV2.build(
            self.completed, attempt=2, previous_run_id=self.first.run_id,
        )
        self.assertNotEqual(self.first.run_id, second.run_id)
        overclaim = self.first.document
        overclaim["path"] = "private.json"
        with self.assertRaises(P10SafetyAnalysisJobContractV2Error):
            P10SafetyAnalysisRunRequestV2.from_document(overclaim)

    def test_restart_recovers_active_run_and_latest_index_is_separate(self):
        store = P10SafetyAnalysisJobStoreV2(self.state)
        queued = store.create(self.first)
        self.assertEqual("queued", queued.status)
        restarted = P10SafetyAnalysisJobStoreV2(self.state)
        self.assertEqual((self.first.run_id,), restarted.recover_interrupted())
        latest = restarted.latest_for_job(self.completed.job_id)
        self.assertEqual("failed_retryable", latest.status)
        self.assertTrue((
            self.state / "jobs" / LATEST_NAMESPACE
            / f"{self.completed.job_id}.json"
        ).is_file())
        self.assertEqual((), restarted.recover_interrupted())

    def test_zero_event_crash_window_is_repaired_idempotently(self):
        directory = run_directory(
            self.state, self.first.run_id, create=True,
        )
        publish_once(directory / "request.json", self.first.canonical_bytes)
        exact_directory(directory, "events", create=True)
        store = P10SafetyAnalysisJobStoreV2(self.state)
        self.assertEqual((self.first.run_id,), store.recover_interrupted())
        latest = store.latest_for_job(self.completed.job_id)
        self.assertEqual(2, len(latest.events))
        self.assertEqual("queued", latest.events[0].document["status"])
        self.assertEqual("failed_retryable", latest.status)
        self.assertEqual((), store.recover_interrupted())

    def test_attempt_chain_advances_after_terminal_and_index_is_o1(self):
        store = P10SafetyAnalysisJobStoreV2(self.state)
        first = store.create(self.first)
        first = store.append(
            first.run_id, "failed_retryable", "failed",
            expected_previous=first.head_event_sha256,
            failure_code="analysis_failed",
        )
        second_request = P10SafetyAnalysisRunRequestV2.build(
            self.completed, attempt=2, previous_run_id=first.run_id,
        )
        second = store.create(second_request)
        with patch.object(
            store, "_run_ids", side_effect=AssertionError("full scan"),
        ):
            latest = store.latest_for_job(self.completed.job_id)
        self.assertEqual(second.run_id, latest.run_id)
        self.assertEqual(2, latest.request.document["attempt"])

    def test_recovery_rebuilds_missing_or_corrupt_latest_index(self):
        store = P10SafetyAnalysisJobStoreV2(self.state)
        snapshot = store.create(self.first)
        store.append(
            snapshot.run_id, "failed_retryable", "failed",
            expected_previous=snapshot.head_event_sha256,
            failure_code="analysis_failed",
        )
        index = self.state / "jobs" / LATEST_NAMESPACE \
            / f"{self.completed.job_id}.json"
        index.unlink()
        store.recover_interrupted()
        self.assertEqual(self.first.run_id,
                         store.latest_for_job(self.completed.job_id).run_id)
        index.write_text('{"bad":true}', encoding="utf-8")
        store.recover_interrupted()
        self.assertEqual(self.first.run_id,
                         store.latest_for_job(self.completed.job_id).run_id)

    def test_dedicated_json_io_round_trips_more_than_two_mebibytes(self):
        directory = self.state / "large"
        directory.mkdir()
        document = {"padding": "x" * (2 * 1024 * 1024 + 17)}
        payload = json.dumps(
            document, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        target = directory / "continuous.json"
        publish_once(target, payload, 3 * 1024 * 1024)
        self.assertEqual(document, read_json(target, 3 * 1024 * 1024))

    def test_event_contract_bounds_and_stage_state(self):
        queued = P10SafetyAnalysisRunEventV2.build(
            self.first.run_id, 1, None, "queued", "queued",
        )
        self.assertEqual("queued", queued.document["status"])
        with self.assertRaises(P10SafetyAnalysisJobContractV2Error):
            P10SafetyAnalysisRunEventV2.build(
                self.first.run_id, 1, None, "queued",
                "continuous_validation",
            )


if __name__ == "__main__":
    unittest.main()
