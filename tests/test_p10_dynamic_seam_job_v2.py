from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from autospine_workbench.p10_dynamic_seam_auto_inputs_v2 import (
    P10DynamicSeamAutoInputsV2,
)
from autospine_workbench.p10_dynamic_seam_job_v2 import (
    P10DynamicSeamJobStoreV2, P10DynamicSeamJobV2Error,
    _require_event, _require_request,
)


class P10DynamicSeamJobV2Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = P10DynamicSeamJobStoreV2(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def test_request_and_run_hash_are_deterministic(self):
        first = self.store.create(_inputs(), attempt=1, previous_run_id=None)
        second = self.store.create(_inputs(), attempt=1, previous_run_id=None)
        self.assertEqual(first.run_id, second.run_id)
        self.assertEqual(first.request, second.request)
        self.assertEqual(first.status, "queued")

    def test_attempt_chain_and_binding_are_version_isolated(self):
        first = self.store.create(_inputs(), attempt=1, previous_run_id=None)
        first = self.store.append(
            first.run_id, "failed_retryable", "failed",
            expected_previous=first.head_sha256,
            failure_code="compile_failed",
        )
        second = self.store.create(
            _inputs(), attempt=2, previous_run_id=first.run_id,
        )
        self.assertEqual(
            self.store.latest("1" * 64, "2" * 64).run_id, second.run_id,
        )
        self.assertNotEqual(first.run_id, second.run_id)

    def test_ambiguous_attempt_predecessor_fails_closed(self):
        self.store.create(_inputs(), attempt=1, previous_run_id=None)
        with self.assertRaises(P10DynamicSeamJobV2Error):
            self.store.create(_inputs(), attempt=2,
                              previous_run_id="f" * 64)

    def test_latest_does_not_scan_unrelated_run_namespace(self):
        row = self.store.create(_inputs(), attempt=1, previous_run_id=None)
        self.store._run_ids = lambda: (_ for _ in ()).throw(
            AssertionError("latest must not scan all runs")
        )
        self.assertEqual(
            self.store.latest("1" * 64, "2" * 64).run_id, row.run_id,
        )

    def test_missing_or_corrupt_index_rebuilds_authoritative_attempt_two(self):
        first = self.store.create(_inputs(), attempt=1, previous_run_id=None)
        first = self.store.append(
            first.run_id, "failed_retryable", "failed",
            expected_previous=first.head_sha256, failure_code="retryable",
        )
        second = self.store.create(
            _inputs(), attempt=2, previous_run_id=first.run_id,
        )
        index = next((self.root / "jobs" /
                      "body-sway-dynamic-seam-latest-v2").iterdir())
        index.unlink()
        self.assertEqual(self.store.latest("1" * 64, "2" * 64).run_id,
                         second.run_id)
        index.write_bytes(b"{}")
        self.assertEqual(self.store.latest("1" * 64, "2" * 64).run_id,
                         second.run_id)

    def test_startup_recovery_writes_retryable_immutable_receipt(self):
        row = self.store.create(_inputs(), attempt=1, previous_run_id=None)
        row = self.store.append(
            row.run_id, "running", "compile_segments",
            expected_previous=row.head_sha256,
        )
        self.assertEqual(self.store.recover_interrupted(), (row.run_id,))
        recovered = self.store.load(row.run_id)
        self.assertEqual(recovered.status, "failed_retryable")
        self.assertEqual(recovered.events[-1]["failure_code"], "process_restart")
        self.assertEqual(recovered.events[-2]["status"], "running")

    def test_malformed_request_fields_fail_closed(self):
        row = self.store.create(
            _inputs(), attempt=1, previous_run_id=None,
        ).request
        attacks = (
            {**row, "project_id": "../escape"},
            {**row, "attempt": 0},
            {**row, "review_revision": 0},
            {**row, "previous_run_id": "f" * 64},
        )
        for attack in attacks:
            with self.subTest(attack=attack):
                with self.assertRaises(P10DynamicSeamJobV2Error):
                    _require_request(attack)

    def test_event_extra_field_and_status_payload_fail_closed(self):
        row = self.store.create(
            _inputs(), attempt=1, previous_run_id=None,
        )
        event = dict(row.events[-1])
        with self.assertRaises(P10DynamicSeamJobV2Error):
            _require_event({**event, "extra": True}, row.run_id, 1)
        event["failure_code"] = "unexpected"
        with self.assertRaises(P10DynamicSeamJobV2Error):
            _require_event(event, row.run_id, 1)


def _inputs():
    return P10DynamicSeamAutoInputsV2(
        "1" * 64, "2" * 64, "package-a", "project-a",
        "3" * 64, "4" * 64, "5" * 64, "6" * 64, 1,
        "7" * 64, "8" * 64,
    )


if __name__ == "__main__":
    unittest.main()
