"""One-shot, no-real-Runtime execution tests for P10.7b v2."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.p10_spine42_v3_runtime_execution_v2 import (  # noqa: E402
    execute_p10_spine42_v3_runtime_job_v2,
)
from autospine_workbench.p10_spine42_v3_runtime_job_store_v2 import (  # noqa: E402
    P10Spine42V3RuntimeJobConflictV2,
)
from autospine_workbench.spine42_v3_runtime_reader_v2 import (  # noqa: E402
    Spine42V3RuntimeReaderV2Error, Spine42V3RuntimeV2NotFound,
)
from tests.p10_spine42_v3_runtime_execution_v2_support import (  # noqa: E402
    ExecutionV2Fixture, PublishBoundary,
)
from tests.p10_spine42_v3_runtime_preflight_v2_support import (  # noqa: E402
    PreflightV2Fixture,
)


class P10Spine42V3RuntimeExecutionV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.source = PreflightV2Fixture(cls.root / "source")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.fixture = ExecutionV2Fixture(
            self.root / self._testMethodName, self.source)

    def tearDown(self):
        self.fixture.close()

    def _execute(self, **dependencies):
        fixture = self.fixture
        return execute_p10_spine42_v3_runtime_job_v2(
            fixture.store, fixture.preflight, fixture.authority,
            fixture.permit, **fixture.dependencies(**dependencies),
        )

    def test_success_has_exact_chain_and_invokes_runner_once(self):
        runner = Mock(return_value=self.fixture.run)
        result = self._execute(runner=runner)
        self.assertEqual(("completed", True),
                         (result.outcome, result.runner_invoked))
        self.assertEqual([
            "queued", "exact_source_readback", "runtime_reverified",
            "capturing", "capturing", "evidence_compiling", "publishing",
            "parent_exact_readback", "completed",
        ], [event.document["stage"] for event in result.snapshot.events])
        runner.assert_called_once()
        public = result.public_document()
        self.assertFalse(public["runner_execution_authorized"])
        self.assertFalse(public["publication_authorized"])
        self.assertNotIn(str(self.root), repr(public))

    def test_execution_preflight_drift_requires_new_authorization_before_runner(self):
        self.fixture.preflight._revalidate = Mock(
            side_effect=RuntimeError("candidate drift"))
        runner = Mock()
        result = self._execute(runner=runner)
        self.assertEqual("failed_retryable", result.snapshot.status)
        self.assertEqual("execution_preflight_changed",
                         result.snapshot.head["failure_code"])
        self.assertEqual("new_authorization",
                         result.snapshot.head["resume_mode"])
        runner.assert_not_called()

    def test_runner_failure_is_retryable_and_never_retried(self):
        runner = Mock(side_effect=RuntimeError("simulated runner failure"))
        result = self._execute(runner=runner)
        self.assertEqual("failed_retryable", result.snapshot.status)
        self.assertEqual("runtime_capture_failed",
                         result.snapshot.head["failure_code"])
        self.assertEqual("new_authorization",
                         result.snapshot.head["resume_mode"])
        runner.assert_called_once()

    def test_invalid_evidence_is_terminal_after_one_runner_call(self):
        runner = Mock(return_value=self.fixture.run)
        invalid = Mock(side_effect=ValueError("invalid evidence"))
        result = self._execute(
            runner=runner, evidence_builder=invalid)
        self.assertEqual("failed_terminal", result.snapshot.status)
        self.assertEqual("evidence_compiling", result.snapshot.head["stage"])
        self.assertEqual("runtime_evidence_invalid",
                         result.snapshot.head["failure_code"])
        runner.assert_called_once()

    def test_publish_is_always_decided_by_exact_readback(self):
        publisher = PublishBoundary(RuntimeError("uncertain publication"))
        result = self._execute(publisher=publisher)
        self.assertEqual("completed", result.snapshot.status)
        self.assertEqual([self.fixture.evidence], publisher.calls)

    def test_publish_not_found_is_retryable(self):
        readback = Mock(side_effect=Spine42V3RuntimeV2NotFound("missing"))
        result = self._execute(readback=readback)
        self.assertEqual("failed_retryable", result.snapshot.status)
        self.assertEqual("capture_address_not_found",
                         result.snapshot.head["failure_code"])
        self.assertEqual("new_authorization",
                         result.snapshot.head["resume_mode"])

    def test_publish_mismatch_is_terminal(self):
        readback = Mock(side_effect=Spine42V3RuntimeReaderV2Error("mismatch"))
        result = self._execute(readback=readback)
        self.assertEqual("failed_terminal", result.snapshot.status)
        self.assertEqual("capture_readback_mismatch",
                         result.snapshot.head["failure_code"])

    def test_cas_conflict_reloads_and_does_not_run(self):
        original_load = self.fixture.store.load
        self.fixture.store.append_event = Mock(
            side_effect=P10Spine42V3RuntimeJobConflictV2("stale"))
        self.fixture.store.load = original_load
        runner = Mock()
        result = self._execute(runner=runner)
        self.assertEqual("conflict_reloaded", result.outcome)
        self.assertEqual("exact_source_readback", result.snapshot.head["stage"])
        runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
