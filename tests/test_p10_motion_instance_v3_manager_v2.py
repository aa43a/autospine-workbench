from __future__ import annotations

from concurrent.futures import Future
from pathlib import Path
import sys
from types import SimpleNamespace
import threading
import unittest
from unittest.mock import patch

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
from autospine_workbench.p10_motion_instance_v3_manager_v2 import (
    P10MotionInstanceV3ManagerV2, P10MotionInstanceV3ManagerV2Error,
)


MODULE = "autospine_workbench.p10_motion_instance_v3_manager_v2."


class MotionInstanceV3ManagerV2Tests(unittest.TestCase):
    def test_entry_returns_attempt_and_completed_submit_is_idempotent(self):
        manager, store = _manager(_row("completed"))
        with patch(MODULE + "resolve_p10_motion_instance_v3_auto_inputs_v2",
                   return_value=_inputs()):
            entry = manager.entry("1" * 64, "2" * 64, "3" * 64)
            submitted = manager.submit("1" * 64, "2" * 64, "3" * 64)
        self.assertEqual("completed", entry["status"])
        self.assertEqual("completed", submitted["status"])
        self.assertEqual([], store.created)

    def test_retryable_creates_new_immutable_attempt(self):
        manager, store = _manager(_row("failed_retryable"))
        with patch(MODULE + "resolve_p10_motion_instance_v3_auto_inputs_v2",
                   return_value=_inputs()):
            value = manager.submit("1" * 64, "2" * 64, "3" * 64)
        self.assertEqual(2, value["run"]["attempt"])
        self.assertEqual((2, "1" * 64), store.created[0])

    def test_terminal_and_changed_inputs_fail_closed(self):
        manager, _ = _manager(_row("failed_terminal"))
        with patch(MODULE + "resolve_p10_motion_instance_v3_auto_inputs_v2",
                   return_value=_inputs()), self.assertRaises(
            P10MotionInstanceV3ManagerV2Error,
        ):
            manager.submit("1" * 64, "2" * 64, "3" * 64)
        changed = P10MotionInstanceV3AutoInputsV2(
            **{**_inputs().identity,
               "dynamic_seam_bundle_sha256": "9" * 64}
        )
        manager, _ = _manager(_row("completed"))
        with patch(MODULE + "resolve_p10_motion_instance_v3_auto_inputs_v2",
                   return_value=changed), self.assertRaises(
            P10MotionInstanceV3ManagerV2Error,
        ):
            manager.entry("1" * 64, "2" * 64, "3" * 64)

    def test_worker_uses_only_automatic_p10_5d_project_and_hashes(self):
        row = _row("queued")
        manager, store = _manager(row)
        command = SimpleNamespace(
            mode="compiled", project_id="project-a", clip_id="idle",
            motion_instance_v3_sha256="6" * 64,
            bundle_sha256="7" * 64, run_sha256="8" * 64,
            reused=False, document={
                "project_id": "project-a",
                "source": {
                    "dynamic_seam_probe_sha256": "4" * 64,
                    "dynamic_seam_bundle_sha256": "5" * 64,
                },
                "address": {
                    "motion_instance_v3_sha256": "6" * 64,
                    "bundle_sha256": "7" * 64,
                },
                "run_sha256": "8" * 64,
                "inventory": list(DOCUMENT_NAMES),
                "verification": {
                    "status": "passed", "exact_readback": True,
                },
            },
        )
        with patch(MODULE +
                   "resolve_p10_motion_instance_v3_auto_inputs_v2",
                   return_value=_inputs()), patch(
            MODULE + "_ReadOnlyCaptureJobs", return_value="capture",
        ), patch(
            MODULE + "compile_body_sway_motion_instance_v3_v2_command",
            return_value=command,
        ) as compile_command:
            manager._run(row.run_id)
        compile_command.assert_called_once_with(
            "capture", manager._projects, "project-a",
            dynamic_seam_probe_sha256="4" * 64,
            dynamic_seam_bundle_sha256="5" * 64,
        )
        self.assertEqual("completed", store.value.status)
        self.assertEqual(list(DOCUMENT_NAMES),
                         store.value.events[-1]["result"]["inventory"])
        self.assertEqual([
            "exact_inputs", "motion_consumer_admission",
            "motion_instance_v3", "publication", "parent_exact_readback",
            "completed",
        ], store.stages)

    def test_result_delegates_exact_historical_verification(self):
        manager, _ = _manager(_row("completed"))
        expected = {"ok": True, "status": "completed"}
        with patch(MODULE + "read_p10_motion_instance_v3_result_v2",
                   return_value=expected) as read:
            value = manager.result(
                "1" * 64, "2" * 64, "3" * 64, "1" * 64,
            )
        self.assertEqual(expected, value)
        read.assert_called_once()


class _Row:
    def __init__(self, status, attempt=1, previous=None, result=None):
        self.status, self.run_id = status, str(attempt) * 64
        self.request = {**_inputs().identity, "attempt": attempt,
                        "previous_run_id": previous}
        self.head_sha256 = "e" * 64
        self.events = ({"result": result},)

    def public_document(self):
        return {"run_id": self.run_id, "status": self.status,
                "attempt": self.request["attempt"]}


class _Store:
    def __init__(self, latest):
        self.value, self.created, self.stages = latest, [], []

    def latest(self, *_):
        return self.value

    def load(self, _run):
        return self.value

    def create(self, _inputs, *, attempt, previous_run_id):
        self.created.append((attempt, previous_run_id))
        self.value = _row("queued", attempt, previous_run_id)
        return self.value

    def append(self, _run, status, stage, **kwargs):
        self.stages.append(stage)
        result = kwargs.get("result")
        self.value.status = status
        self.value.head_sha256 = str(len(self.stages)) * 64
        self.value.events = self.value.events + ({"result": result},)
        return self.value


class _Executor:
    def submit(self, *_):
        return Future()


def _manager(latest):
    manager = object.__new__(P10MotionInstanceV3ManagerV2)
    store = _Store(latest)
    manager._projects = SimpleNamespace(state_root="state")
    manager._store, manager._executor = store, _Executor()
    manager._lock, manager._cancel = threading.RLock(), threading.Event()
    manager._futures, manager._closed = {}, False
    return manager, store


def _row(status, attempt=1, previous=None):
    result = None
    if status == "completed":
        result = {
            "project_id": "project-a", "clip_id": "idle",
            "motion_instance_v3_sha256": "6" * 64,
            "bundle_sha256": "7" * 64, "run_sha256": "8" * 64,
            "inventory": list(DOCUMENT_NAMES), "reused": False,
        }
    return _Row(status, attempt, previous, result)


def _inputs():
    return P10MotionInstanceV3AutoInputsV2(
        "1" * 64, "2" * 64, "3" * 64, "project-a",
        "4" * 64, "5" * 64,
    )


if __name__ == "__main__":
    unittest.main()
