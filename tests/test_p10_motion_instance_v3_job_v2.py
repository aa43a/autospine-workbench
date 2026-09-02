from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.motion_instance_v3_bundle_contract_v2 import (
    DOCUMENT_NAMES,
)
from autospine_workbench.p10_motion_instance_v3_auto_inputs_v2 import (
    P10MotionInstanceV3AutoInputsV2,
)
from autospine_workbench.p10_motion_instance_v3_job_contract_v2 import (
    P10MotionInstanceV3JobV2Error, require_event, require_request,
)
from autospine_workbench.p10_motion_instance_v3_job_v2 import (
    P10MotionInstanceV3JobStoreV2,
)


class MotionInstanceV3JobV2Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = P10MotionInstanceV3JobStoreV2(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def test_deterministic_address_o1_latest_and_attempt_chain(self):
        first = self.store.create(_inputs(), attempt=1, previous_run_id=None)
        again = self.store.create(_inputs(), attempt=1, previous_run_id=None)
        self.assertEqual(first.run_id, again.run_id)
        first = self.store.append(
            first.run_id, "failed_retryable", "failed",
            expected_previous=first.head_sha256,
            failure_code="compile_failed",
        )
        second = self.store.create(
            _inputs(), attempt=2, previous_run_id=first.run_id,
        )
        self.store._run_ids = lambda: (_ for _ in ()).throw(
            AssertionError("valid latest index must not scan")
        )
        latest = self.store.latest("1" * 64, "2" * 64, "3" * 64)
        self.assertEqual(second.run_id, latest.run_id)

    def test_corrupt_index_rebuilds_and_restart_is_retryable(self):
        row = self.store.create(_inputs(), attempt=1, previous_run_id=None)
        row = self.store.append(
            row.run_id, "running", "exact_inputs",
            expected_previous=row.head_sha256,
        )
        index = next((self.root / "jobs" /
                      "body-sway-motion-instance-v3-latest-v2").iterdir())
        index.write_bytes(b"{}")
        self.assertEqual(row.run_id, self.store.latest(
            "1" * 64, "2" * 64, "3" * 64,
        ).run_id)
        self.assertEqual((row.run_id,), self.store.recover_interrupted())
        recovered = self.store.load(row.run_id)
        self.assertEqual("failed_retryable", recovered.status)
        self.assertEqual("process_restart",
                         recovered.events[-1]["failure_code"])

    def test_completed_inventory_and_tokens_are_closed(self):
        row = self.store.create(_inputs(), attempt=1, previous_run_id=None)
        row = self.store.append(
            row.run_id, "running", "exact_inputs",
            expected_previous=row.head_sha256,
        )
        result = _result()
        event = _event(row, result)
        require_event(event, row.run_id, len(row.events) + 1)
        for attack in (
            {**result, "inventory": ["arbitrary.json"]},
            {**result, "project_id": "../escape"},
            {**result, "reused": 1},
        ):
            with self.subTest(attack=attack), self.assertRaises(
                P10MotionInstanceV3JobV2Error,
            ):
                require_event(_event(row, attack), row.run_id,
                              len(row.events) + 1)

    def test_request_rejects_cross_version_extra_and_bad_project(self):
        request = self.store.create(
            _inputs(), attempt=1, previous_run_id=None,
        ).request
        for attack in (
            {**request, "format_version": 1},
            {**request, "project_id": "../escape"},
            {**request, "extra": True},
        ):
            with self.assertRaises(P10MotionInstanceV3JobV2Error):
                require_request(attack)


def _inputs():
    return P10MotionInstanceV3AutoInputsV2(
        "1" * 64, "2" * 64, "3" * 64, "project-a",
        "4" * 64, "5" * 64,
    )


def _result():
    return {
        "project_id": "project-a", "clip_id": "idle",
        "motion_instance_v3_sha256": "6" * 64,
        "bundle_sha256": "7" * 64, "run_sha256": "8" * 64,
        "inventory": list(DOCUMENT_NAMES), "reused": False,
    }


def _event(row, result):
    from autospine_workbench.p10_motion_instance_v3_job_contract_v2 import (
        EVENT_FORMAT,
    )
    from autospine_workbench.resolved_project import canonical_sha256
    payload = {
        "format": EVENT_FORMAT, "format_version": 2,
        "run_id": row.run_id, "sequence": len(row.events) + 1,
        "previous_event_sha256": row.head_sha256,
        "status": "completed", "stage": "completed",
        "progress": {"current": 1, "total": 1},
        "failure_code": None, "result": result,
    }
    return {**payload, "event_sha256": canonical_sha256({
        "domain": "autospine-p10-motion-instance-v3-job-event/v2",
        "event": payload,
    })}


if __name__ == "__main__":
    unittest.main()
