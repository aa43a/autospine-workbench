"""Exact-readback recovery tests for P10.7b v2 runtime jobs."""

from __future__ import annotations

import inspect
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import autospine_workbench.p10_spine42_v3_runtime_recovery_v2 as subject
import autospine_workbench.spine42_v3_runtime_reader_v2 as reader_subject
from autospine_workbench.p10_spine42_v3_runtime_job_contract_v2 import (
    P10Spine42V3RuntimeJobRequestV2,
)
from autospine_workbench.p10_spine42_v3_runtime_job_store_v2 import (
    P10Spine42V3RuntimeJobConflictV2,
    P10Spine42V3RuntimeJobStoreV2,
)
from autospine_workbench.spine42_v3_runtime_reader_v2 import (
    Spine42V3RuntimeReaderV2Error,
    Spine42V3RuntimeV2NotFound,
)
from autospine_workbench.spine42_v3_runtime_store_v2 import Spine42V3RuntimeStoreV2
from tests.spine42_v3_runtime_storage_v2_helpers import RuntimeStorageV2Fixture
from tests.test_p10_spine42_v3_runtime_job_contract_v2 import _browser, _runtime


class _ReaderFailure:
    def __init__(self, error):
        self.error = error

    def load(self, *_address):
        if isinstance(self.error, BaseException):
            raise self.error
        return self.error


class P10Spine42V3RuntimeRecoveryV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.fixture = RuntimeStorageV2Fixture(cls.root / "fixture")
        cls.state_root = cls.fixture.state_root
        with cls.fixture.profile():
            Spine42V3RuntimeStoreV2(cls.state_root).publish(
                cls.fixture.evidence
            )
        bundle = cls.fixture.bundle
        cls.address = {
            "project_id": bundle.project_id,
            "skeleton_json_sha256": bundle.skeleton_json_sha256,
            "spine42_v3_bundle_sha256": bundle.spine42_v3_bundle_sha256,
            "capture_bundle_sha256": bundle.bundle_sha256,
        }
        cls.sequence = 0

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.store = P10Spine42V3RuntimeJobStoreV2(self.state_root)

    def _request(self, *, clip_id=None, runtime=None, browser=None):
        type(self).sequence += 1
        number = type(self).sequence
        payload = {
            "candidate_id": f"{number:064x}",
            "entry_sha256": f"{number + 1000:064x}",
            "authorization_id": f"recover-auth-{number:08d}",
            "retry_of_job_id": None,
            "explicit_runtime_license_confirmation": True,
            "explicit_run_confirmation": True,
        }
        bundle = self.fixture.bundle
        return P10Spine42V3RuntimeJobRequestV2.expand(
            payload, project_id=bundle.project_id,
            clip_id=clip_id or bundle.clip_id,
            skeleton_json_sha256=bundle.skeleton_json_sha256,
            spine42_v3_bundle_sha256=bundle.spine42_v3_bundle_sha256,
            runtime=runtime or self.fixture.runtime,
            browser=browser or self.fixture.browser,
        )

    def _reach(self, stage, *, address=None, clip_id=None, request=None):
        row = self.store.create(request or self._request(clip_id=clip_id))
        for current_stage in (
            "exact_source_readback", "runtime_reverified",
        ):
            row = self.store.append_event(
                row.job_id, "running", current_stage,
                expected_previous_event_sha256=row.head_event_sha256,
            )
        row = self.store.append_event(
            row.job_id, "running", "capturing",
            expected_previous_event_sha256=row.head_event_sha256,
            current=0, total=1,
        )
        if stage == "capturing":
            return row
        row = self.store.append_event(
            row.job_id, "running", "capturing",
            expected_previous_event_sha256=row.head_event_sha256,
            current=1, total=1,
        )
        row = self.store.append_event(
            row.job_id, "running", "evidence_compiling",
            expected_previous_event_sha256=row.head_event_sha256,
        )
        row = self.store.append_event(
            row.job_id, "running", "publishing",
            expected_previous_event_sha256=row.head_event_sha256,
            capture_address=address or self.address,
        )
        if stage == "publishing":
            return row
        return self.store.append_event(
            row.job_id, "running", "parent_exact_readback",
            expected_previous_event_sha256=row.head_event_sha256,
            capture_address=address or self.address,
        )

    def _recover(self, **kwargs):
        upstream = Mock()
        upstream.load.return_value = self.fixture.upstream
        with patch.object(
            reader_subject, "VerifiedSpine42V3BundleReaderV2",
            return_value=upstream,
        ), self.fixture.profile():
            return subject.recover_p10_spine42_v3_runtime_jobs_v2(
                self.store, **kwargs
            )

    def test_publishing_is_exact_read_then_parent_then_completed_once(self):
        row = self._reach("publishing")
        before = len(row.events)
        result = self._recover()
        final = self.store.load(row.job_id)
        self.assertEqual("completed", final.status)
        self.assertEqual(before + 2, len(final.events))
        self.assertEqual(
            ["parent_exact_readback", "completed"],
            [event.document["stage"] for event in final.events[-2:]],
        )
        self.assertEqual(self.address, final.head["result"])
        self.assertEqual("completed", result.items[0].outcome)
        repeat = self._recover()
        self.assertEqual((), repeat.readback_required_job_ids)
        self.assertEqual(before + 2, len(self.store.load(row.job_id).events))

    def test_parent_readback_completes_without_repeating_parent_stage(self):
        row = self._reach("parent_exact_readback")
        before = len(row.events)
        result = self._recover()
        final = self.store.load(row.job_id)
        self.assertEqual(before + 1, len(final.events))
        self.assertEqual("completed", final.status)
        self.assertEqual("completed", result.items[0].outcome)

    def test_not_found_is_retryable_at_the_same_late_stage(self):
        for stage in ("publishing", "parent_exact_readback"):
            with self.subTest(stage=stage):
                row = self._reach(stage)
                result = self._recover(reader_factory=lambda _root: _ReaderFailure(
                    Spine42V3RuntimeV2NotFound("absent")
                ))
                final = self.store.load(row.job_id)
                self.assertEqual("failed_retryable", final.status)
                self.assertEqual(stage, final.head["stage"])
                self.assertEqual("capture_address_not_found",
                                 final.head["failure_code"])
                self.assertEqual("new_authorization",
                                 final.head["resume_mode"])
                self.assertEqual("failed_retryable", result.items[-1].outcome)

    def test_corrupt_or_nonissued_readback_is_terminal(self):
        failures = (
            Spine42V3RuntimeReaderV2Error("corrupt"), object(),
        )
        for index, failure in enumerate(failures):
            with self.subTest(index=index):
                row = self._reach("publishing")
                result = self._recover(
                    reader_factory=lambda _root, value=failure:
                        _ReaderFailure(value)
                )
                final = self.store.load(row.job_id)
                self.assertEqual("failed_terminal", final.status)
                self.assertEqual("publishing", final.head["stage"])
                self.assertEqual("capture_readback_mismatch",
                                 final.head["failure_code"])
                self.assertIsNone(final.head["resume_mode"])
                self.assertEqual("failed_terminal", result.items[-1].outcome)

    def test_reader_issued_clip_mismatch_is_terminal(self):
        row = self._reach("publishing", clip_id="different-clip")
        result = self._recover()
        final = self.store.load(row.job_id)
        self.assertEqual("failed_terminal", final.status)
        self.assertEqual("capture_readback_mismatch",
                         final.head["failure_code"])
        self.assertEqual("failed_terminal", result.items[0].outcome)

    def test_reader_issued_runtime_or_browser_mismatch_is_terminal(self):
        for environment in ({"runtime": _runtime()}, {"browser": _browser()}):
            with self.subTest(field=next(iter(environment))):
                request = self._request(**environment)
                row = self._reach("publishing", request=request)
                result = self._recover()
                final = self.store.load(row.job_id)
                self.assertEqual("failed_terminal", final.status)
                self.assertEqual(
                    "capture_readback_mismatch", final.head["failure_code"])
                self.assertEqual("failed_terminal", result.items[-1].outcome)

    def test_reader_issued_evidence_must_match_all_four_address_parts(self):
        wrong = dict(self.address)
        wrong["capture_bundle_sha256"] = "f" * 64
        row = self._reach("publishing", address=wrong)
        upstream = Mock()
        upstream.load.return_value = self.fixture.upstream
        with patch.object(
            reader_subject, "VerifiedSpine42V3BundleReaderV2",
            return_value=upstream,
        ), self.fixture.profile():
            issued = reader_subject.VerifiedSpine42V3RuntimeReaderV2(
                self.state_root
            ).load(*self.address.values())
        result = self._recover(
            reader_factory=lambda _root: _ReaderFailure(issued)
        )
        final = self.store.load(row.job_id)
        self.assertEqual("failed_terminal", final.status)
        self.assertEqual("capture_readback_mismatch",
                         final.head["failure_code"])
        self.assertEqual("failed_terminal", result.items[0].outcome)

    def test_reader_issued_same_address_from_another_root_is_terminal(self):
        row = self._reach("publishing")
        other = self.root / f"cross-root-{row.job_id[:8]}"
        __import__("shutil").copytree(self.state_root, other)
        upstream = Mock()
        upstream.load.return_value = self.fixture.upstream
        with patch.object(reader_subject, "VerifiedSpine42V3BundleReaderV2",
                          return_value=upstream), self.fixture.profile():
            issued = reader_subject.VerifiedSpine42V3RuntimeReaderV2(
                other).load(*self.address.values())
        self._recover(reader_factory=lambda _root: _ReaderFailure(issued))
        final = self.store.load(row.job_id)
        self.assertEqual("failed_terminal", final.status)
        self.assertEqual("capture_readback_mismatch", final.head["failure_code"])

    def test_cas_conflict_only_reloads_the_concurrent_terminal_head(self):
        row = self._reach("publishing")
        original = self.store.append_event
        called = False

        def concurrent_completion(*args, **kwargs):
            nonlocal called
            if called:
                return original(*args, **kwargs)
            called = True
            parent = original(*args, **kwargs)
            original(
                parent.job_id, "completed", "completed",
                expected_previous_event_sha256=parent.head_event_sha256,
                current=1, total=1, result=self.address,
            )
            raise P10Spine42V3RuntimeJobConflictV2("lost CAS")

        with patch.object(
            self.store, "append_event", side_effect=concurrent_completion,
        ):
            result = self._recover()
        final = self.store.load(row.job_id)
        self.assertEqual("completed", final.status)
        self.assertEqual("conflict_reloaded", result.items[0].outcome)
        self.assertEqual("completed", result.items[0].status)
        self.assertEqual((), self._recover().items)

    def test_early_recovery_precedes_readback_and_public_is_path_free(self):
        early = self._reach("capturing")
        late = self._reach("publishing")
        result = self._recover()
        self.assertIn(early.job_id, result.interrupted_job_ids)
        self.assertIn(late.job_id, result.readback_required_job_ids)
        self.assertEqual("interrupted_retryable",
                         self.store.load(early.job_id).status)
        public = result.public_document()
        self.assertFalse(public["runner_execution_authorized"])
        self.assertFalse(public["publication_authorized"])
        self.assertNotIn(str(self.state_root), repr(public))
        self.assertNotIn("path", repr(public).lower())

    def test_module_has_no_runtime_execution_dependency(self):
        source = inspect.getsource(subject)
        self.assertNotIn("runtime_runner", source)
        self.assertFalse(any(name.startswith("run_spine42")
                             for name in vars(subject)))


if __name__ == "__main__":
    unittest.main()
