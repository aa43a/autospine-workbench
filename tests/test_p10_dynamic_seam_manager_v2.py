from __future__ import annotations

from concurrent.futures import Future
from types import SimpleNamespace
import threading
import unittest
from unittest.mock import patch

from autospine_workbench.p10_dynamic_seam_auto_inputs_v2 import (
    P10DynamicSeamAutoInputsV2,
)
from autospine_workbench.p10_dynamic_seam_manager_v2 import (
    P10DynamicSeamManagerV2, P10DynamicSeamManagerV2Error,
)


class ManagerV2Tests(unittest.TestCase):
    def test_entry_returns_terminal_receipt_instead_of_ready(self):
        manager, store = _manager(_row("failed_retryable"))
        with patch(_RESOLVE, return_value=_inputs()):
            value = manager.entry("1" * 64, "2" * 64)
        self.assertEqual(value["status"], "failed_retryable")
        self.assertEqual(value["run"]["attempt"], 1)

    def test_completed_submit_is_idempotent(self):
        completed = _row("completed")
        manager, store = _manager(completed)
        with patch(_RESOLVE, return_value=_inputs()):
            value = manager.submit("1" * 64, "2" * 64)
        self.assertEqual(value["status"], "completed")
        self.assertEqual(store.created, [])

    def test_terminal_failure_cannot_retry(self):
        manager, _ = _manager(_row("failed_terminal"))
        with patch(_RESOLVE, return_value=_inputs()), self.assertRaises(
            P10DynamicSeamManagerV2Error
        ):
            manager.submit("1" * 64, "2" * 64)

    def test_retryable_requires_explicit_submit_and_creates_attempt_two(self):
        manager, store = _manager(_row("failed_retryable"))
        with patch(_RESOLVE, return_value=_inputs()):
            manager.entry("1" * 64, "2" * 64)
            self.assertEqual(store.created, [])
            value = manager.submit("1" * 64, "2" * 64)
        self.assertEqual(store.created[0][0], 2)
        self.assertEqual(value["run"]["attempt"], 2)

    def test_changed_current_inputs_fail_closed(self):
        manager, _ = _manager(_row("completed"))
        changed = P10DynamicSeamAutoInputsV2(
            **{**_inputs().identity, "decision_sha256": "9" * 64}
        )
        with patch(_RESOLVE, return_value=changed), self.assertRaises(
            P10DynamicSeamManagerV2Error
        ):
            manager.entry("1" * 64, "2" * 64)

    def test_parent_rejects_stale_crosswired_or_release_overclaim(self):
        manager, _ = _manager(_row("running"))
        row, result, verified = _parent_values()
        reader = SimpleNamespace(load=lambda *_: verified)
        with patch(_RESOLVE, return_value=_inputs()), patch(
            _READER, return_value=reader
        ):
            manager._verify_parent(row, result)
            changed = P10DynamicSeamAutoInputsV2(
                **{**_inputs().identity, "decision_sha256": "9" * 64}
            )
            with patch(_RESOLVE, return_value=changed), self.assertRaises(
                P10DynamicSeamManagerV2Error
            ):
                manager._verify_parent(row, result)
            with self.assertRaises(P10DynamicSeamManagerV2Error):
                manager._verify_parent(row, {**result,
                                              "probe_sha256": "f" * 64})
            verified.probe["claims"]["release_authority"] = True
            with self.assertRaises(P10DynamicSeamManagerV2Error):
                manager._verify_parent(row, result)


class _Row:
    def __init__(self, status, attempt=1, previous=None):
        self.status, self.run_id = status, str(attempt) * 64
        self.request = {**_inputs().identity, "attempt": attempt,
                        "previous_run_id": previous}
        self.head_sha256 = "e" * 64
        self.events = ({"result": None},)

    def public_document(self):
        return {"run_id": self.run_id, "status": self.status,
                "attempt": self.request["attempt"],
                "previous_run_id": self.request["previous_run_id"]}


class _Store:
    def __init__(self, latest):
        self.value, self.created = latest, []

    def latest(self, *_):
        return self.value

    def create(self, inputs, *, attempt, previous_run_id):
        self.created.append((attempt, previous_run_id))
        self.value = _Row("queued", attempt, previous_run_id)
        return self.value


class _Executor:
    def submit(self, *_):
        return Future()


def _manager(latest):
    manager = object.__new__(P10DynamicSeamManagerV2)
    store = _Store(latest)
    manager._projects = SimpleNamespace(state_root="state", workspace_root="work")
    manager._store, manager._executor = store, _Executor()
    manager._lock, manager._cancel = threading.RLock(), threading.Event()
    manager._futures, manager._closed = {}, False
    return manager, store


def _row(status):
    return _Row(status)


def _inputs():
    return P10DynamicSeamAutoInputsV2(
        "1" * 64, "2" * 64, "package-a", "project-a", "3" * 64,
        "4" * 64, "5" * 64, "6" * 64, 1, "7" * 64, "8" * 64,
    )


def _parent_values():
    row = _Row("running")
    result = {"project_id": "project-a", "clip_id": "clip-a",
              "probe_sha256": "a" * 64, "bundle_sha256": "b" * 64,
              "source_set_sha256": "c" * 64,
              "source_document_sha256": "d" * 64,
              "probe_status": "compiled"}
    verified = SimpleNamespace(
        project_id="project-a", clip_id="clip-a", probe_sha256="a" * 64,
        bundle_sha256="b" * 64, source_set_sha256="c" * 64,
        source_document_sha256="d" * 64,
        source={
            "body_sway_continuous_preview_proof_v2_sha256": "3" * 64,
            "reviewed_seam_anchor_set_v1_sha256": "4" * 64,
            "reviewed_seam_anchor_set_v1_bundle_sha256": "5" * 64,
        },
        probe={"status": "compiled", "release_gate": {"status": "blocked"},
               "claims": {"release_authority": False}},
    )
    return row, result, verified


_RESOLVE = (
    "autospine_workbench.p10_dynamic_seam_manager_v2."
    "resolve_p10_dynamic_seam_auto_inputs_v2"
)
_READER = (
    "autospine_workbench.p10_dynamic_seam_manager_v2."
    "BodySwayDynamicSeamBundleReaderV2"
)


if __name__ == "__main__":
    unittest.main()
