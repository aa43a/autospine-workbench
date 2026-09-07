"""Lifecycle tests for the P10.7b v2 single-worker manager."""

from __future__ import annotations

from concurrent.futures import Future
from pathlib import Path
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.p10_spine42_v3_runtime_manager_owner_lease_v2 import (  # noqa: E402
    P10Spine42V3RuntimeManagerOwnerLeaseV2,
)
from autospine_workbench.p10_spine42_v3_runtime_manager_v2 import (  # noqa: E402
    P10Spine42V3RuntimeManagerV2, P10Spine42V3RuntimeManagerV2Error,
)
from autospine_workbench.p10_spine42_v3_runtime_preflight_v2 import (  # noqa: E402
    P10Spine42V3RuntimePreflightV2,
)
from autospine_workbench.project_store import ProjectStore  # noqa: E402
from tests.p10_spine42_v3_runtime_preflight_v2_support import (  # noqa: E402
    BridgeFactory, PreflightV2Fixture,
)


class _DeferredExecutor:
    def __init__(self, *, fail_submit=False):
        self.future, self.fail_submit, self.shutdown_called = (
            Future(), fail_submit, False,
        )

    def submit(self, *_args):
        if self.fail_submit:
            raise RuntimeError("private enqueue failure")
        return self.future

    def shutdown(self, *, wait, cancel_futures):
        self.shutdown_called = wait and cancel_futures


class P10Spine42V3RuntimeManagerV2Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.workspace, self.state = self.root / "input", self.root / "state"
        self.workspace.mkdir()
        self.state.mkdir()
        self.projects = ProjectStore(
            self.workspace, self.state, measure_composite_quality=False)
        self.fixture = PreflightV2Fixture(self.root / "fixture")
        self.executions = 0

    def tearDown(self):
        self.temporary.cleanup()

    def _preflight(self, state_root):
        fixture = self.fixture
        return P10Spine42V3RuntimePreflightV2(
            state_root,
            candidate_revalidator=lambda *_: fixture.candidate,
            catalog_reader=lambda *_: fixture.catalog(),
            bridge_factory=BridgeFactory(fixture),
            environment_discovery=lambda *_: fixture.environment,
        )

    def _manager(self, execution=None, **kwargs):
        def settle(store, _preflight, authority, permit):
            self.executions += 1
            context = authority.consume(permit)
            snapshot = store.load(context.job_id)
            store.append_event(
                snapshot.job_id, "failed_retryable", snapshot.head["stage"],
                expected_previous_event_sha256=snapshot.head_event_sha256,
                failure_code="test_execution_done",
                resume_mode="new_authorization",
            )

        return P10Spine42V3RuntimeManagerV2(
            self.projects, execution=execution or settle,
            preflight_factory=self._preflight,
            catalog_reader=lambda _root, **_kwargs: self.fixture.catalog(),
            **kwargs,
        )

    def test_duplicate_submit_claims_and_executes_at_most_once(self):
        started, release = threading.Event(), threading.Event()

        def execution(store, _preflight, authority, permit):
            self.executions += 1
            context = authority.consume(permit)
            started.set()
            release.wait(10)
            snapshot = store.load(context.job_id)
            store.append_event(
                snapshot.job_id, "failed_retryable", snapshot.head["stage"],
                expected_previous_event_sha256=snapshot.head_event_sha256,
                failure_code="test_execution_done",
                resume_mode="new_authorization",
            )

        manager = self._manager(execution)
        try:
            first = manager.submit(
                self.fixture.payload(), selection_source="automatic")
            self.assertTrue(started.wait(5))
            second = manager.submit(
                self.fixture.payload(), selection_source="automatic")
            self.assertEqual(first["job_id"], second["job_id"])
            self.assertEqual(2, second["event_count"])
            self.assertEqual(1, self.executions)
        finally:
            release.set()
            manager.close()
        self.assertEqual("failed_retryable", manager.get(first["job_id"])["status"])

    def test_second_manager_is_rejected_then_release_allows_takeover(self):
        first = self._manager()
        with self.assertRaises(P10Spine42V3RuntimeManagerV2Error):
            self._manager()
        first.close()
        second = self._manager()
        second.close()

    def test_constructor_failure_releases_owner_lease(self):
        def failure(_root):
            raise RuntimeError("private construction failure")

        with self.assertRaises(P10Spine42V3RuntimeManagerV2Error) as caught:
            self._manager(store_factory=failure)
        self.assertNotIn(str(self.root), str(caught.exception))
        lease = P10Spine42V3RuntimeManagerOwnerLeaseV2(self.state).acquire()
        lease.close()

    def test_enqueue_failure_is_retryable_and_path_free(self):
        executor = _DeferredExecutor(fail_submit=True)
        manager = self._manager(executor_factory=lambda **_kwargs: executor)
        try:
            row = manager.submit(
                self.fixture.payload(), selection_source="automatic")
            self.assertEqual("failed_retryable", row["status"])
            self.assertEqual("execution_enqueue_failed", row["failure_code"])
            self.assertEqual("new_authorization", row["resume_mode"])
            self.assertEqual(0, self.executions)
        finally:
            manager.close()
        self.assertTrue(executor.shutdown_called)

    def test_authority_failure_does_not_leave_an_active_claim(self):
        captured = {}

        def store_factory(root):
            from autospine_workbench.p10_spine42_v3_runtime_job_store_v2 import (
                P10Spine42V3RuntimeJobStoreV2,
            )
            captured["store"] = P10Spine42V3RuntimeJobStoreV2(root)
            return captured["store"]

        class RejectingAuthority:
            def issue(self, *_args):
                raise RuntimeError("private authority failure")

        manager = self._manager(
            store_factory=store_factory,
            authority_factory=lambda _store, _lease: RejectingAuthority(),
        )
        ready = self._preflight(self.state).prepare(
            self.fixture.payload(), selection_source="automatic")
        ready = self._preflight(self.state).refresh_for_create(ready)
        try:
            with self.assertRaises(P10Spine42V3RuntimeManagerV2Error):
                manager.submit(
                    self.fixture.payload(), selection_source="automatic")
            final = captured["store"].load(ready.request.job_id)
            self.assertEqual("failed_retryable", final.status)
            self.assertEqual(
                "execution_authority_failed", final.head["failure_code"])
        finally:
            manager.close()

    def test_late_execution_failure_is_left_for_exact_readback_recovery(self):
        address = {
            "project_id": self.fixture.bundle.project_id,
            "skeleton_json_sha256": self.fixture.bundle.skeleton_json_sha256,
            "spine42_v3_bundle_sha256": self.fixture.bundle.bundle_sha256,
            "capture_bundle_sha256": "f" * 64,
        }

        def execution(store, _preflight, authority, permit):
            context = authority.consume(permit)
            row = store.load(context.job_id)
            for stage, current, total in (
                ("runtime_reverified", 0, 1), ("capturing", 0, 1),
                ("capturing", 1, 1), ("evidence_compiling", 0, 1),
            ):
                row = store.append_event(
                    row.job_id, "running", stage,
                    expected_previous_event_sha256=row.head_event_sha256,
                    current=current, total=total,
                )
            store.append_event(
                row.job_id, "running", "publishing",
                expected_previous_event_sha256=row.head_event_sha256,
                capture_address=address,
            )
            raise RuntimeError("private late execution failure")

        manager = self._manager(execution)
        row = manager.submit(
            self.fixture.payload(), selection_source="automatic")
        manager.close()
        final = manager.get(row["job_id"])
        self.assertEqual("running", final["status"])
        self.assertEqual("publishing", final["stage"])

    def test_close_cancels_pending_burns_permit_and_interrupts(self):
        executor = _DeferredExecutor()
        manager = self._manager(executor_factory=lambda **_kwargs: executor)
        row = manager.submit(
            self.fixture.payload(), selection_source="automatic")
        manager.close()
        final = manager.get(row["job_id"])
        self.assertEqual("interrupted_retryable", final["status"])
        self.assertEqual("manager_closed", final["failure_code"])
        self.assertEqual(0, self.executions)
        with self.assertRaises(P10Spine42V3RuntimeManagerV2Error):
            manager.submit(
                self.fixture.payload(), selection_source="automatic")

    def test_close_waits_for_started_worker(self):
        started, release, closed = (
            threading.Event(), threading.Event(), threading.Event())

        def execution(store, _preflight, authority, permit):
            context = authority.consume(permit)
            started.set()
            release.wait(10)
            snapshot = store.load(context.job_id)
            store.append_event(
                snapshot.job_id, "failed_retryable", snapshot.head["stage"],
                expected_previous_event_sha256=snapshot.head_event_sha256,
                failure_code="test_execution_done",
                resume_mode="new_authorization",
            )

        manager = self._manager(execution)
        manager.submit(self.fixture.payload(), selection_source="automatic")
        self.assertTrue(started.wait(5))
        closer = threading.Thread(
            target=lambda: (manager.close(), closed.set()))
        closer.start()
        self.assertFalse(closed.wait(.1))
        release.set()
        closer.join(5)
        self.assertTrue(closed.is_set())
        takeover = self._manager()
        takeover.close()

    def test_catalog_is_read_only_and_never_executes(self):
        manager = self._manager()
        try:
            before = _tree(self.state)
            document = manager.catalog()
            after = _tree(self.state)
            self.assertEqual(before, after)
            self.assertEqual("automatic", document["selection"]["mode"])
            self.assertEqual(0, self.executions)
        finally:
            manager.close()


def _tree(root):
    return tuple(sorted(
        (path.relative_to(root).as_posix(), path.stat().st_size,
         path.stat().st_mtime_ns)
        for path in root.rglob("*") if path.is_file()
    ))


if __name__ == "__main__":
    unittest.main()
