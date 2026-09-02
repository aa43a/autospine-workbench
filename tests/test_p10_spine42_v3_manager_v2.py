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

from autospine_workbench.p10_spine42_v3_auto_inputs_v2 import (
    P10Spine42V3AutoInputsV2,
)
from autospine_workbench.p10_spine42_v3_job_contract_v2 import DOCUMENT_NAMES
from autospine_workbench.p10_spine42_v3_manager_v2 import (
    P10Spine42V3ManagerV2, P10Spine42V3ManagerV2Error,
)

MODULE = "autospine_workbench.p10_spine42_v3_manager_v2."


class Spine42V3ManagerV2Tests(unittest.TestCase):
    def test_completed_submit_is_idempotent(self):
        manager, store = _manager(_row("completed"))
        with patch(MODULE + "resolve_p10_spine42_v3_auto_inputs_v2",
                   return_value=_inputs()):
            entry = manager.entry(*_ids())
            submitted = manager.submit(*_ids())
        self.assertEqual("completed", entry["status"])
        self.assertEqual("completed", submitted["status"])
        self.assertEqual([], store.created)

    def test_retryable_creates_new_attempt_but_terminal_does_not(self):
        manager, store = _manager(_row("failed_retryable"))
        with patch(MODULE + "resolve_p10_spine42_v3_auto_inputs_v2",
                   return_value=_inputs()):
            value = manager.submit(*_ids())
        self.assertEqual(2, value["run"]["attempt"])
        self.assertEqual((2, "1" * 64), store.created[0])
        manager, _ = _manager(_row("failed_terminal"))
        with patch(MODULE + "resolve_p10_spine42_v3_auto_inputs_v2",
                   return_value=_inputs()), self.assertRaises(
            P10Spine42V3ManagerV2Error,
        ):
            manager.submit(*_ids())

    def test_changed_exact_motion_source_fails_closed(self):
        changed = P10Spine42V3AutoInputsV2(
            **{**_inputs().identity,
               "motion_instance_v3_bundle_sha256": "9" * 64}
        )
        manager, _ = _manager(_row("completed"))
        with patch(MODULE + "resolve_p10_spine42_v3_auto_inputs_v2",
                   return_value=changed), self.assertRaises(
            P10Spine42V3ManagerV2Error,
        ):
            manager.entry(*_ids())

    def test_entry_submit_worker_exact_reads_p10_6b_once(self):
        manager, store = _manager(None)
        motion = object()
        command = SimpleNamespace(
            mode="compiled", project_id="project-a", clip_id="idle",
            skeleton_json_sha256="7" * 64, bundle_sha256="8" * 64,
            run_document_sha256="9" * 64, report_sha256="a" * 64,
            inventory=DOCUMENT_NAMES, reused=False,
            document={
                "project_id": "project-a",
                "address": {
                    "skeleton_json_sha256": "7" * 64,
                    "bundle_sha256": "8" * 64,
                },
                "inventory": list(DOCUMENT_NAMES),
                "verification": {
                    "status": "passed", "exact_readback": True,
                },
            },
        )
        with patch(MODULE + "resolve_p10_spine42_v3_auto_inputs_v2",
                   return_value=_inputs()) as resolve, patch(
            MODULE + "load_verified_p10_spine42_v3_motion_v2",
            return_value=motion,
        ) as exact_source, patch(
            MODULE + "_ReadOnlyCaptureJobs", return_value="capture",
        ), patch(
            MODULE + "compile_verified_body_sway_spine42_v3_v2_command",
            return_value=command,
        ) as compile_command:
            entry = manager.entry(*_ids())
            submitted = manager.submit(*_ids())
            manager._run(submitted["run"]["run_id"])
        self.assertEqual("ready", entry["status"])
        self.assertEqual("queued", submitted["status"])
        self.assertEqual(4, resolve.call_count)
        exact_source.assert_called_once_with("state", _inputs())
        compile_command.assert_called_once_with(
            "capture", manager._projects, motion,
        )
        self.assertEqual("completed", store.value.status)
        self.assertEqual(list(DOCUMENT_NAMES),
                         store.value.events[-1]["result"]["inventory"])
        self.assertEqual([
            "exact_motion_instance", "source_adapter", "spine_adapter",
            "publication", "parent_exact_readback", "completed",
        ], store.stages)

    def test_worker_fails_closed_when_sealed_journal_drifts_at_end(self):
        changed = P10Spine42V3AutoInputsV2(
            **{**_inputs().identity,
               "motion_instance_v3_bundle_sha256": "9" * 64}
        )
        manager, store = _manager(_row("queued"))
        with patch(
            MODULE + "resolve_p10_spine42_v3_auto_inputs_v2",
            side_effect=(_inputs(), changed),
        ), patch(
            MODULE + "load_verified_p10_spine42_v3_motion_v2",
            return_value=object(),
        ), patch(
            MODULE + "compile_verified_body_sway_spine42_v3_v2_command",
            return_value=_command(),
        ), patch(MODULE + "_ReadOnlyCaptureJobs", return_value="capture"):
            manager._run(store.value.run_id)
        self.assertEqual("failed_terminal", store.value.status)
        self.assertEqual("parent_validation_failed",
                         store.value.events[-1]["failure_code"])

    def test_result_replays_exact_historical_bundle_every_time(self):
        manager, _ = _manager(_row("completed"))
        expected = {"ok": True, "status": "completed"}
        with patch(MODULE + "read_p10_spine42_v3_result_v2",
                   return_value=expected) as read:
            first = manager.result(*_ids(), "1" * 64)
            second = manager.result(*_ids(), "1" * 64)
        self.assertEqual(expected, first)
        self.assertEqual(expected, second)
        self.assertEqual(2, read.call_count)


class _Row:
    def __init__(self, status, attempt=1, previous=None, result=None):
        self.status, self.run_id = status, str(attempt) * 64
        self.request = {
            **_inputs().identity, "attempt": attempt,
            "previous_run_id": previous,
        }
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
        self.value.status = status
        self.value.head_sha256 = str(len(self.stages)) * 64
        self.value.events += ({
            "result": kwargs.get("result"),
            "failure_code": kwargs.get("failure_code"),
        },)
        return self.value


class _Executor:
    def submit(self, *_):
        return Future()


def _manager(latest):
    manager = object.__new__(P10Spine42V3ManagerV2)
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
            "skeleton_json_sha256": "7" * 64,
            "bundle_sha256": "8" * 64,
            "run_document_sha256": "9" * 64,
            "report_sha256": "a" * 64,
            "inventory": list(DOCUMENT_NAMES), "reused": False,
        }
    return _Row(status, attempt, previous, result)


def _inputs():
    return P10Spine42V3AutoInputsV2(
        *_ids(), "project-a", "5" * 64, "6" * 64,
    )


def _ids():
    return "1" * 64, "2" * 64, "3" * 64, "4" * 64


def _command():
    return SimpleNamespace(
        mode="compiled", project_id="project-a", clip_id="idle",
        skeleton_json_sha256="7" * 64, bundle_sha256="8" * 64,
        run_document_sha256="9" * 64, report_sha256="a" * 64,
        inventory=DOCUMENT_NAMES, reused=False,
        document={
            "project_id": "project-a",
            "address": {
                "skeleton_json_sha256": "7" * 64,
                "bundle_sha256": "8" * 64,
            },
            "inventory": list(DOCUMENT_NAMES),
            "verification": {"status": "passed", "exact_readback": True},
        },
    )


if __name__ == "__main__":
    unittest.main()
