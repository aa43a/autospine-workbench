"""Fast-entry, attempt, cancellation, cache, and redaction tests."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.p10_safety_analysis_job_contract_v2 import (  # noqa: E402
    P10SafetyAnalysisRunRequestV2,
)
from autospine_workbench.p10_safety_analysis_manager_v2 import (  # noqa: E402
    P10SafetyAnalysisManagerV2,
)
from autospine_workbench.p10_safety_analysis_public_cache_v2 import (  # noqa: E402
    MAX_PUBLIC_CACHE_BYTES,
    P10SafetyAnalysisPublicCacheV2,
)
from autospine_workbench.p10_safety_analysis_result_v2 import (  # noqa: E402
    public_result,
)
from autospine_workbench.p10_safety_analysis_v2_commands import (  # noqa: E402
    P10SafetyAnalysisV2CommandError,
)
from autospine_workbench.p10_safety_analysis_worker_process_v2 import (  # noqa: E402
    P10SafetyAnalysisWorkerResultV2,
)
from tests.p10_safety_analysis_job_v2_test_helpers import (  # noqa: E402
    SHA,
    completed_capture_job,
)
from tests.test_project_store import StoreFixture  # noqa: E402


class _Jobs:
    def __init__(self, document):
        self.document = document
        self.calls = 0

    def get(self, job_id):
        self.calls += 1
        if self.document["job_id"] != job_id:
            raise KeyError(job_id)
        return self.document


class P10SafetyAnalysisManagerV2Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = StoreFixture(Path(self.temporary.name))
        self.projects = self.fixture.store()
        self.completed = completed_capture_job()
        self.jobs = _Jobs(self.completed.public_snapshot())
        self.manager = P10SafetyAnalysisManagerV2(
            self.jobs, self.projects,
        )

    def tearDown(self):
        self.manager.close()
        self.temporary.cleanup()

    def test_entry_is_constant_work_and_submit_is_asynchronous(self):
        started, release = threading.Event(), threading.Event()

        def blocking(*args, **kwargs):
            started.set()
            release.wait(5)
            raise P10SafetyAnalysisV2CommandError("stop")

        with patch(
            "autospine_workbench.p10_safety_analysis_manager_v2."
            "run_p10_safety_analysis_worker_process_v2",
            side_effect=blocking,
        ) as compile_mock:
            before = time.perf_counter()
            entry = self.manager.entry(self.completed.job_id)
            self.assertLess(time.perf_counter() - before, 0.5)
            self.assertEqual("ready", entry["status"])
            compile_mock.assert_not_called()
            before = time.perf_counter()
            first = self.manager.submit(self.completed.job_id)
            self.assertLess(time.perf_counter() - before, 0.5)
            self.assertTrue(started.wait(2))
            duplicate = self.manager.submit(self.completed.job_id)
            self.assertEqual(first["run"]["run_id"],
                             duplicate["run"]["run_id"])
            future = self.manager._futures[first["run"]["run_id"]]
            release.set()
            future.result(timeout=2)
            restarted = P10SafetyAnalysisManagerV2(
                self.jobs, self.projects,
            )
            try:
                self.assertEqual(
                    "ready", restarted.entry(self.completed.job_id)["status"],
                )
            finally:
                restarted.close()

    def test_completed_attempt_never_silently_reuses_on_fresh_submit(self):
        request = P10SafetyAnalysisRunRequestV2.build(
            self.completed, attempt=1, previous_run_id=None,
        )
        first = self.manager._store.create(request)
        sealed = _sealed_result()
        first = self.manager._store.append(
            first.run_id, "completed", "completed",
            expected_previous=first.head_event_sha256,
            current=1, total=1, result=sealed,
        )
        blocker = threading.Event()

        def blocked(*args, **kwargs):
            blocker.wait(5)
            raise P10SafetyAnalysisV2CommandError("stop")

        with patch(
            "autospine_workbench.p10_safety_analysis_manager_v2."
            "run_p10_safety_analysis_worker_process_v2",
            side_effect=blocked,
        ):
            response = self.manager.submit(self.completed.job_id)
            second = self.manager._store.load(response["run"]["run_id"])
            self.assertNotEqual(first.run_id, second.run_id)
            self.assertEqual(2, second.request.document["attempt"])
            self.assertEqual(first.run_id,
                             second.request.document["previous_run_id"])
            future = self.manager._futures[second.run_id]
            blocker.set()
            future.result(timeout=2)

    def test_close_is_bounded_and_marks_active_work_retryable(self):
        started, release = threading.Event(), threading.Event()

        def blocked(*args, **kwargs):
            started.set()
            release.wait(5)
            raise P10SafetyAnalysisV2CommandError("stop")

        with patch(
            "autospine_workbench.p10_safety_analysis_manager_v2."
            "run_p10_safety_analysis_worker_process_v2",
            side_effect=blocked,
        ):
            response = self.manager.submit(self.completed.job_id)
            self.assertTrue(started.wait(2))
            future = self.manager._futures[response["run"]["run_id"]]
            before = time.perf_counter()
            self.manager.close()
            self.assertLess(time.perf_counter() - before, 0.5)
            snapshot = self.manager._store.load(
                response["run"]["run_id"],
            )
            self.assertEqual("failed_retryable", snapshot.status)
            self.assertEqual("manager_closed",
                             snapshot.events[-1].document["failure_code"])
            release.set()
            future.result(timeout=2)
            restarted = P10SafetyAnalysisManagerV2(
                self.jobs, self.projects,
            )
            try:
                self.assertEqual(
                    "ready", restarted.entry(self.completed.job_id)["status"],
                )
            finally:
                restarted.close()

    def test_command_failure_classification_is_preserved_in_receipt(self):
        failures = (
            ("analysis_validation_failed", True, "failed_terminal"),
            ("source_unavailable", False, "failed_retryable"),
        )
        previous_run_id = None
        for code, terminal, expected_status in failures:
            with self.subTest(code=code), patch(
                "autospine_workbench.p10_safety_analysis_manager_v2."
                "run_p10_safety_analysis_worker_process_v2",
                side_effect=P10SafetyAnalysisV2CommandError(
                    "stop", failure_code=code, terminal=terminal,
                ),
            ):
                response = self.manager.submit(self.completed.job_id)
                run_id = response["run"]["run_id"]
                self.assertNotEqual(previous_run_id, run_id)
                self.manager._futures[run_id].result(timeout=2)
                snapshot = self.manager._store.load(run_id)
                self.assertEqual(expected_status, snapshot.status)
                self.assertEqual(
                    code, snapshot.events[-1].document["failure_code"],
                )
                previous_run_id = run_id

    def test_result_is_path_free_and_full_documents_are_not_cached(self):
        request = P10SafetyAnalysisRunRequestV2.build(
            self.completed, attempt=1, previous_run_id=None,
        )
        snapshot = self.manager._store.create(request)
        snapshot = self.manager._store.append(
            snapshot.run_id, "completed", "completed",
            expected_previous=snapshot.head_event_sha256,
            current=1, total=1, result=_sealed_result(),
        )
        amplitude, continuous = _public_documents()
        with patch.object(
            self.manager._store, "read_result",
            return_value=(amplitude, continuous),
        ) as read:
            first = self.manager.result(
                self.completed.job_id, snapshot.run_id,
            )
            second = self.manager.result(
                self.completed.job_id, snapshot.run_id,
            )
        self.assertEqual(first, second)
        read.assert_called_once_with(snapshot.run_id)
        self.assertEqual(self.completed.job_id, first["job_id"])
        self.assertEqual("compile_time_snapshot",
                         first["authority_scope"])
        self.assertFalse(any("path" in key.lower()
                             for key in _recursive_keys(first)))
        self.assertNotIn("source", first["documents"]["amplitude"])

    def test_worker_result_is_reverified_before_completed_event(self):
        amplitude, continuous = _public_documents()
        worker_result = P10SafetyAnalysisWorkerResultV2(
            _sealed_result(), amplitude, continuous,
        )
        with patch(
            "autospine_workbench.p10_safety_analysis_manager_v2."
            "run_p10_safety_analysis_worker_process_v2",
            return_value=worker_result,
        ), patch.object(
            self.manager._store, "verify_staged_result",
            return_value=(amplitude, continuous),
        ) as verify, patch(
            "autospine_workbench.p10_safety_analysis_manager_v2."
            "verify_parent_p10_safety_analysis_result_v2",
            side_effect=lambda jobs, projects, store, run_id, result:
                store.verify_staged_result(run_id, result.result),
        ) as parent_verify:
            response = self.manager.submit(self.completed.job_id)
            run_id = response["run"]["run_id"]
            self.manager._futures[run_id].result(timeout=2)
        snapshot = self.manager._store.load(run_id)
        self.assertEqual("completed", snapshot.status)
        verify.assert_called_once_with(run_id, worker_result.result)
        parent_verify.assert_called_once()
        self.assertEqual("completed", self.manager.result(
            self.completed.job_id, run_id,
        )["status"])

    def test_box_heartbeat_is_throttled_before_store_replay(self):
        request = P10SafetyAnalysisRunRequestV2.build(
            self.completed, attempt=1, previous_run_id=None,
        )
        snapshot = self.manager._store.create(request)
        snapshot = self.manager._store.append(
            snapshot.run_id, "running", "review_admission",
            expected_previous=snapshot.head_event_sha256,
            current=0, total=1,
        )
        self.manager._progress_memory[snapshot.run_id] = (
            "review_admission", 0, 1,
        )
        with patch.object(
            self.manager._store, "load",
            wraps=self.manager._store.load,
        ) as load:
            self.manager._progress(
                snapshot.run_id, "continuous_boxes", 0, 32_768,
            )
            for current in range(1, 657):
                self.manager._progress(
                    snapshot.run_id, "continuous_boxes",
                    current, 32_768,
                )
        # Three persisted heartbeats; each append performs exact pre/readback.
        self.assertEqual(9, load.call_count)
        latest = self.manager._store.load(snapshot.run_id)
        self.assertEqual(
            {"current": 656, "total": 32_768},
            latest.events[-1].document["progress"],
        )

    def test_public_cache_is_single_entry_and_byte_bounded(self):
        cache = P10SafetyAnalysisPublicCacheV2()
        cache.put("a" * 64, {"value": 1})
        self.assertEqual({"value": 1}, cache.get("a" * 64))
        cache.put("b" * 64, {"padding": "x" * MAX_PUBLIC_CACHE_BYTES})
        self.assertIsNone(cache.get("a" * 64))
        self.assertIsNone(cache.get("b" * 64))


def _sealed_result():
    return {
        "authority_scope": "compile_time_snapshot",
        "admission_sha256": SHA["1"],
        "visual_candidate_sha256": SHA["2"], "visual_revision": 1,
        "visual_decision_sha256": SHA["3"],
        "amplitude_sha256": SHA["4"],
        "continuous_sha256": SHA["5"],
        "amplitude_size_bytes": 123, "continuous_size_bytes": 456,
    }


def _public_documents():
    amplitude = {
        "format": "autospine-body-sway-amplitude-envelope-candidate",
        "format_version": 2, "status": "candidate_only",
        "image_path": "E:/private/amplitude.png",
        "probes": [{
            "gain": {"numerator": index, "denominator": 8},
            "status": "sampled_structural_passed",
            "visual_review_status": (
                "official_runtime_sampled_cases_approved"
                if index == 8 else "not_reviewed"
            ),
        } for index in range(9)],
    }
    continuous = {
        "format": "autospine-body-sway-continuous-preview-proof",
        "format_version": 2, "project_id": "fixture-project",
        "clip_id": "wave-left-v1", "status": "indeterminate",
        "source": {"path": "E:/private/continuous.json"},
        "summary": {
            "segment_count": 1, "certified_segment_count": 0,
            "indeterminate_segment_count": 1,
        },
        "segments": [{
            "left_tick": 0, "right_tick": 1, "status": "indeterminate",
            "reason_codes": ["canvas_containment_unproven"],
        }],
        "claims": {
            "continuous_preview_model_structural_safety": False,
            "uniform_gain_zero_to_reviewed_structurally_certified": False,
            "official_runtime_continuous_equivalence": False,
            "visual_gain_range": False, "reviewed_seam_anchors": False,
            "motion_instance_v3": False, "publishable_timeline": False,
            "release_authority": False,
        },
        "release_gate": {
            "status": "blocked", "reason_codes": ["preview_model_only"],
        },
    }
    return amplitude, continuous


def _recursive_keys(value):
    if isinstance(value, dict):
        result = set(value)
        for item in value.values():
            result.update(_recursive_keys(item))
        return result
    if isinstance(value, list):
        result = set()
        for item in value:
            result.update(_recursive_keys(item))
        return result
    return set()


if __name__ == "__main__":
    unittest.main()
