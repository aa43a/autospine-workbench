"""Cross-process serialization tests for P10.7b v2 job transactions."""

from __future__ import annotations

import multiprocessing
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.p10_spine42_v3_runtime_job_contract_v2 import (
    P10Spine42V3RuntimeJobRequestV2,
)
import autospine_workbench.p10_spine42_v3_runtime_job_process_lock_v2 as lock_module
from autospine_workbench.p10_spine42_v3_runtime_job_process_lock_v2 import (
    runtime_job_process_lock_v2,
)
from autospine_workbench.p10_spine42_v3_runtime_job_store_v2 import (
    P10Spine42V3RuntimeJobStoreV2, P10Spine42V3RuntimeJobStoreV2Error,
)
from tests.test_p10_spine42_v3_runtime_job_store_v2 import _request


def _paused_create(root, request_document, entered, release, output):
    import autospine_workbench.p10_spine42_v3_runtime_job_store_v2 as module
    real_bind = module.bind_runtime_job_attempt_v2

    def pause_before_binding(*args, **kwargs):
        entered.set()
        if not release.wait(10):
            raise RuntimeError("test release timed out")
        return real_bind(*args, **kwargs)

    try:
        request = P10Spine42V3RuntimeJobRequestV2.from_document(
            request_document)
        with patch.object(module, "bind_runtime_job_attempt_v2",
                          side_effect=pause_before_binding):
            row = P10Spine42V3RuntimeJobStoreV2(root).create(request)
        output.put(("create", row.status, row.job_id))
    except Exception as exc:
        output.put(("create_error", type(exc).__name__, str(exc)))


def _concurrent_recovery(root, started, done, output):
    started.set()
    try:
        result = P10Spine42V3RuntimeJobStoreV2(root).recover_interrupted()
        output.put(("recover", result.interrupted_job_ids))
    except Exception as exc:
        output.put(("recover_error", type(exc).__name__, str(exc)))
    finally:
        done.set()


class P10Spine42V3RuntimeJobProcessLockV2Tests(unittest.TestCase):
    def test_transaction_body_exception_is_not_rewrapped(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(RuntimeError, "body sentinel"):
                with runtime_job_process_lock_v2(Path(temporary)):
                    raise RuntimeError("body sentinel")

    def test_store_operations_normalize_lock_acquisition_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = P10Spine42V3RuntimeJobStoreV2(Path(temporary))
            request, row = _request(), store.create(_request())
            actions = (
                lambda: store.create(request),
                lambda: store.append_event(
                    row.job_id, "running", "exact_source_readback",
                    expected_previous_event_sha256=row.head_event_sha256),
                store.recover_interrupted,
            )
            for action in actions:
                with patch.object(lock_module, "_open_lock",
                                  side_effect=OSError("X:/private")):
                    with self.assertRaises(
                        P10Spine42V3RuntimeJobStoreV2Error
                    ) as raised:
                        action()
                self.assertIs(type(raised.exception),
                              P10Spine42V3RuntimeJobStoreV2Error)
                self.assertNotIn("private", str(raised.exception).lower())

    def test_recovery_cannot_delete_another_process_active_staging(self):
        context = multiprocessing.get_context("spawn")
        with tempfile.TemporaryDirectory() as temporary:
            root, request = Path(temporary), _request()
            entered, release = context.Event(), context.Event()
            started, done, output = context.Event(), context.Event(), context.Queue()
            creator = context.Process(
                target=_paused_create,
                args=(root, request.document, entered, release, output))
            recovery = context.Process(
                target=_concurrent_recovery,
                args=(root, started, done, output))
            creator.start()
            try:
                self.assertTrue(entered.wait(10))
                recovery.start()
                self.assertTrue(started.wait(10))
                self.assertFalse(done.wait(0.4))
            finally:
                release.set()
            creator.join(15)
            recovery.join(15)
            self.assertEqual(0, creator.exitcode)
            self.assertEqual(0, recovery.exitcode)
            results = {output.get(timeout=3)[0]: None for _ in range(2)}
            self.assertEqual({"create", "recover"}, set(results))
            row = P10Spine42V3RuntimeJobStoreV2(root).load(request.job_id)
            self.assertEqual("interrupted_retryable", row.status)
            self.assertEqual("new_authorization", row.head["resume_mode"])
            self.assertFalse(row.public_document()[
                "runner_execution_authorized"])


if __name__ == "__main__":
    unittest.main()
