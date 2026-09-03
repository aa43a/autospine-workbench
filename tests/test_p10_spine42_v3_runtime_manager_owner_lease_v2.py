"""Cross-process lifecycle owner tests for P10.7b v2 automation."""

from __future__ import annotations

import multiprocessing
import os
from pathlib import Path
import pickle
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.p10_spine42_v3_runtime_manager_owner_lease_v2 import (  # noqa: E402
    P10Spine42V3RuntimeManagerOwnerLeaseV2,
    P10Spine42V3RuntimeManagerOwnerLeaseV2Error,
    _require_acquired_p10_spine42_v3_runtime_manager_owner_lease_v2,
)


def _child_owner(root, ready, finish, crash):
    lease = P10Spine42V3RuntimeManagerOwnerLeaseV2(root).acquire()
    ready.set()
    finish.wait(15)
    if crash:
        os._exit(23)
    lease.close()


class P10Spine42V3RuntimeManagerOwnerLeaseV2Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_same_process_is_exclusive_close_is_idempotent(self):
        first = P10Spine42V3RuntimeManagerOwnerLeaseV2(self.root).acquire()
        self.assertTrue(first.acquired)
        first_identity = (
            _require_acquired_p10_spine42_v3_runtime_manager_owner_lease_v2(
                first
            )
        )
        with self.assertRaises(P10Spine42V3RuntimeManagerOwnerLeaseV2Error):
            P10Spine42V3RuntimeManagerOwnerLeaseV2(self.root).acquire()
        first.close()
        first.close()
        self.assertFalse(first.acquired)
        with P10Spine42V3RuntimeManagerOwnerLeaseV2(self.root) as second:
            self.assertTrue(second.acquired)
            second_identity = (
                _require_acquired_p10_spine42_v3_runtime_manager_owner_lease_v2(
                    second
                )
            )
            self.assertEqual(first_identity[0], second_identity[0])
            self.assertIsNot(first_identity[1], second_identity[1])
        self.assertFalse(second.acquired)

    def test_exact_current_owner_validation_rejects_closed_or_subclass(self):
        class DerivedLease(P10Spine42V3RuntimeManagerOwnerLeaseV2):
            pass

        closed = P10Spine42V3RuntimeManagerOwnerLeaseV2(self.root)
        for value in (None, closed, DerivedLease(self.root)):
            with self.subTest(value=type(value).__name__), self.assertRaises(
                P10Spine42V3RuntimeManagerOwnerLeaseV2Error
            ):
                _require_acquired_p10_spine42_v3_runtime_manager_owner_lease_v2(
                    value
                )

    def test_cross_process_owner_blocks_then_normal_release_allows_takeover(self):
        process, finish = self._start_child(crash=False)
        try:
            with self.assertRaises(
                P10Spine42V3RuntimeManagerOwnerLeaseV2Error
            ):
                P10Spine42V3RuntimeManagerOwnerLeaseV2(self.root).acquire()
        finally:
            finish.set()
            process.join(15)
        self.assertEqual(0, process.exitcode)
        lease = P10Spine42V3RuntimeManagerOwnerLeaseV2(self.root).acquire()
        lease.close()

    def test_process_crash_releases_owner_lock(self):
        process, finish = self._start_child(crash=True)
        finish.set()
        process.join(15)
        self.assertEqual(23, process.exitcode)
        lease = P10Spine42V3RuntimeManagerOwnerLeaseV2(self.root).acquire()
        self.assertTrue(lease.acquired)
        lease.close()

    def test_lease_is_not_serializable_and_errors_are_path_free(self):
        lease = P10Spine42V3RuntimeManagerOwnerLeaseV2(self.root)
        with self.assertRaises(TypeError):
            pickle.dumps(lease)
        with self.assertRaises(P10Spine42V3RuntimeManagerOwnerLeaseV2Error):
            P10Spine42V3RuntimeManagerOwnerLeaseV2(None)
        lease.acquire()
        (self.root / "jobs" / "body-sway-spine42-v3-runtime-manager-owner-v2"
         / "unexpected").write_text("x", encoding="utf-8")
        lease.close()
        with self.assertRaises(P10Spine42V3RuntimeManagerOwnerLeaseV2Error) as caught:
            P10Spine42V3RuntimeManagerOwnerLeaseV2(self.root).acquire()
        self.assertNotIn(str(self.root), str(caught.exception))

    def _start_child(self, *, crash):
        context = multiprocessing.get_context("spawn")
        ready, finish = context.Event(), context.Event()
        process = context.Process(
            target=_child_owner,
            args=(str(self.root), ready, finish, crash),
        )
        process.start()
        self.assertTrue(ready.wait(15), "child did not acquire owner lease")
        return process, finish


if __name__ == "__main__":
    unittest.main()
