from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from autospine_workbench.p10_spine42_v3_auto_inputs_v2 import (
    P10Spine42V3AutoInputsV2,
)
from autospine_workbench.p10_spine42_v3_job_contract_v2 import DOCUMENT_NAMES
from autospine_workbench.p10_spine42_v3_job_v2 import (
    P10Spine42V3JobStoreV2, P10Spine42V3JobV2Error,
)
from autospine_workbench.p10_capture_job_store import P10CaptureJobStoreError


def _sha(character):
    return character * 64


def _inputs():
    return P10Spine42V3AutoInputsV2(
        _sha("1"), _sha("2"), _sha("3"), _sha("4"), "sample",
        _sha("5"), _sha("6"),
    )


def _result():
    return {
        "project_id": "sample", "clip_id": "idle",
        "skeleton_json_sha256": _sha("7"),
        "bundle_sha256": _sha("8"),
        "run_document_sha256": _sha("9"),
        "report_sha256": _sha("a"),
        "inventory": list(DOCUMENT_NAMES), "reused": False,
    }


class P10Spine42V3JobV2Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = P10Spine42V3JobStoreV2(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def test_run_is_deterministic_and_completed_is_immutable(self):
        first = self.store.create(_inputs(), attempt=1, previous_run_id=None)
        duplicate = self.store.create(
            _inputs(), attempt=1, previous_run_id=None,
        )
        self.assertEqual(first.run_id, duplicate.run_id)
        running = self.store.append(
            first.run_id, "running", "exact_motion_instance",
            expected_previous=first.head_sha256,
        )
        completed = self.store.append(
            first.run_id, "completed", "completed",
            expected_previous=running.head_sha256, current=1, total=1,
            result=_result(),
        )
        self.assertEqual(completed.status, "completed")
        with self.assertRaises(P10Spine42V3JobV2Error):
            self.store.append(
                first.run_id, "running", "source_adapter",
                expected_previous=completed.head_sha256,
            )

    def test_retry_is_new_attempt_and_restart_is_recoverable(self):
        first = self.store.create(_inputs(), attempt=1, previous_run_id=None)
        recovered = self.store.recover_interrupted()
        self.assertEqual(recovered, (first.run_id,))
        failed = self.store.load(first.run_id)
        self.assertEqual(failed.status, "failed_retryable")
        second = self.store.create(
            _inputs(), attempt=2, previous_run_id=first.run_id,
        )
        self.assertNotEqual(first.run_id, second.run_id)
        self.assertEqual(second.request["attempt"], 2)
        self.assertEqual(second.request["previous_run_id"], first.run_id)
        self.assertEqual(
            self.store.latest(
                _sha("1"), _sha("2"), _sha("3"), _sha("4"),
            ).run_id,
            second.run_id,
        )

    def test_event_tampering_fails_closed(self):
        row = self.store.create(_inputs(), attempt=1, previous_run_id=None)
        event = self.root / "jobs" / "body-sway-spine42-v3-jobs-v2" \
            / row.run_id / "events" / "000001.json"
        value = json.loads(event.read_text(encoding="utf-8"))
        value["stage"] = "source_adapter"
        event.chmod(0o644)
        event.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaises((P10Spine42V3JobV2Error,
                                P10CaptureJobStoreError)):
            self.store.load(row.run_id)

    def test_changed_exact_source_creates_distinct_request_address(self):
        first = self.store.create(_inputs(), attempt=1, previous_run_id=None)
        changed = P10Spine42V3AutoInputsV2(
            _sha("1"), _sha("2"), _sha("3"), _sha("4"), "sample",
            _sha("5"), _sha("b"),
        )
        second = self.store.create(
            changed, attempt=2, previous_run_id=first.run_id,
        )
        self.assertNotEqual(first.run_id, second.run_id)
        self.assertNotEqual(
            first.request["motion_instance_v3_bundle_sha256"],
            second.request["motion_instance_v3_bundle_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
