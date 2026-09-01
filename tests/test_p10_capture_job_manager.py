"""Single-worker, authority, progress, failure, and shutdown manager tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.browser_executable_snapshot import (  # noqa: E402
    BrowserExecutableSnapshot,
)
from autospine_workbench.body_sway_headless_browser_inputs import (  # noqa: E402
    BodySwayHeadlessBrowserError,
)
from autospine_workbench.p10_capture_job_manager import (  # noqa: E402
    FORMAT,
    FORMAT_VERSION,
    P10CaptureJobManager,
)
from autospine_workbench.p10_capture_job_store import (  # noqa: E402
    P10CaptureJobStore,
)
from autospine_workbench.p10_preview_v2_commands import (  # noqa: E402
    P10PreviewV2CommandResult,
)
from autospine_workbench.p10_runtime_capture_v2_commands import (  # noqa: E402
    P10RuntimeCaptureV2CommandError,
    P10RuntimeCaptureV2CommandResult,
)
from autospine_workbench.p10_runtime_capture_v2_runner import (  # noqa: E402
    P10RuntimeCaptureV2Progress, P10RuntimeCaptureV2RunnerError,
)
from autospine_workbench.p10_runtime_environment import (  # noqa: E402
    P10RuntimeEnvironment,
)
from autospine_workbench.project_store import ProjectStore  # noqa: E402
from autospine_workbench.spine42_runtime_inputs import (  # noqa: E402
    Spine42RuntimePackage,
)


SHA = {name: character * 64 for name, character in {
    "package": "1", "p10_candidate": "2", "p10_decision": "3",
    "frame_candidate": "4", "frame_decision": "5",
    "preview": "6", "preview_artifact": "7", "execution": "8",
    "capture": "9", "artifact": "a", "bundle": "b",
}.items()}
P10_HEAD = {
    "candidate_sha256": SHA["p10_candidate"],
    "decision_sha256": SHA["p10_decision"], "revision": 3,
}
FRAMING = {
    "candidate_sha256": SHA["frame_candidate"],
    "decision_sha256": SHA["frame_decision"], "revision": 2,
}


class P10CaptureJobManagerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.workspace, self.state = root / "source", root / "state"
        self.workspace.mkdir()
        self.state.mkdir()
        self.projects = ProjectStore(self.workspace, state_root=self.state)
        self.preview = self._preview()
        self.environment = self._environment()
        self.compiler_calls = 0
        self.executor_calls = []
        self.managers = []

    def tearDown(self):
        for manager in self.managers:
            manager.close()
        self.temporary.cleanup()

    def test_prepare_uses_current_preview_and_one_cached_path_free_environment(self):
        environment_calls = []
        manager = self._manager(
            environment_loader=lambda root: (
                environment_calls.append(root) or self.environment
            ),
        )
        self.assertEqual([], environment_calls)
        first = manager.prepare(SHA["package"])
        second = manager.prepare(SHA["package"])
        self.assertEqual(first, second)
        self.assertEqual(FORMAT, first["format"])
        self.assertEqual(FORMAT_VERSION, first["format_version"])
        self.assertEqual({"p10_1": P10_HEAD, "framing": FRAMING}, first["expected"])
        self.assertEqual("ready", first["status"])
        self.assertEqual(1, len(environment_calls))
        self.assertEqual(2, self.compiler_calls)
        self.assertNotIn(str(self.state), repr(first))
        self.assertNotIn("path", repr(first).lower())

    def test_success_records_every_stage_and_exact_completed_addresses(self):
        observed_mount_status = []
        manager = self._manager()
        publication = (
            "autospine_workbench.p10_capture_job_manager."
            "publish_visual_review_mount_best_effort"
        )
        with patch(publication, side_effect=lambda _projects, job_id, _result:
                   observed_mount_status.append(manager.get(job_id)["status"])):
            queued = manager.submit(self._payload("success"))
            completed = manager.wait(queued["job_id"], timeout=5)
        self.assertEqual("queued", queued["status"])
        self.assertEqual("completed", completed["status"])
        self.assertEqual([
            "queued", "exact_replay", "preview_compiled",
            "runtime_verified", "capturing", "capturing", "capturing",
            "sealing", "completed",
        ], [event["status"] for event in completed["events"]])
        self.assertEqual([
            {"current": value, "total": 2} for value in range(3)
        ], [
            event["progress"] for event in completed["events"]
            if event["status"] == "capturing"
        ])
        self.assertEqual({
            "project": "fixture-project", "preview": SHA["preview"],
            "execution_bundle": SHA["bundle"], "artifact": SHA["artifact"],
        }, completed["addresses"])
        self.assertEqual([(P10_HEAD, FRAMING, True, True)], self.executor_calls)
        self.assertEqual(["completed"], observed_mount_status)
        repeated = manager.submit(self._payload("success"))
        self.assertEqual("completed", repeated["status"])
        self.assertEqual(1, len(self.executor_calls))

    def test_unavailable_environment_is_retryable_and_never_executes(self):
        manager = self._manager(environment=P10RuntimeEnvironment(None, None))
        self.assertEqual(
            "runtime_unavailable", manager.prepare(SHA["package"])["status"],
        )
        queued = manager.submit(self._payload("missing-runtime"))
        settled = manager.wait(queued["job_id"], timeout=5)
        self.assertEqual("failed_retryable", settled["status"])
        self.assertEqual("runtime_environment_unavailable", settled["failure_code"])
        self.assertEqual([], self.executor_calls)

    def test_input_identity_drift_is_terminal(self):
        changed = self._preview(p10={**P10_HEAD, "revision": 4})
        manager = self._manager(compiler=lambda *_args: changed)
        queued = manager.submit(self._payload("stale-input"))
        settled = manager.wait(queued["job_id"], timeout=5)
        self.assertEqual("failed_terminal", settled["status"])
        self.assertEqual("input_head_changed", settled["failure_code"])
        self.assertEqual([], self.executor_calls)

    def test_execution_failure_is_retryable_but_same_confirmation_does_not_retry(self):
        def fail(*_args, **_kwargs):
            self.executor_calls.append((
                _kwargs["expected_p10_1"], _kwargs["expected_framing"],
                _kwargs["license_acknowledged"], _kwargs["run_confirmed"],
            ))
            raise P10RuntimeCaptureV2CommandError("private path is unavailable")

        manager = self._manager(executor=fail)
        payload = self._payload("one-attempt")
        submitted = manager.submit(payload)
        settled = manager.wait(submitted["job_id"], timeout=5)
        self.assertEqual("failed_retryable", settled["status"])
        self.assertEqual("runtime_capture_failed", settled["failure_code"])
        self.assertNotIn("private", repr(settled))
        self.assertEqual("failed_retryable", manager.submit(payload)["status"])
        self.assertEqual(1, len(self.executor_calls))
        self.assertFalse(hasattr(manager, "retry"))

    def test_nested_browser_failure_persists_only_its_safe_code(self):
        def fail(*_args, **_kwargs):
            browser = BodySwayHeadlessBrowserError(
                "Headless browser exited without posting the exact capture"
            )
            runner = caused(P10RuntimeCaptureV2RunnerError("runner"), browser)
            raise P10RuntimeCaptureV2CommandError(r"C:\\private\\error.log") \
                from runner

        manager = self._manager(executor=fail)
        queued = manager.submit(self._payload("safe-code"))
        settled = manager.wait(queued["job_id"], timeout=5)
        self.assertEqual(
            "runtime_browser_exited_without_capture",
            settled["failure_code"],
        )
        self.assertNotIn("private", repr(settled))

    def test_startup_marks_old_active_job_interrupted_without_execution(self):
        jobs = P10CaptureJobStore(self.state)
        active = jobs.create(self._payload("old-process"))
        active = jobs.append_event(
            active.job_id, "exact_replay",
            expected_previous_event_sha=active.head_event_sha,
        )
        manager = self._manager()
        self.assertEqual((active.job_id,), manager.recovered_job_ids)
        self.assertEqual("interrupted_retryable", manager.get(active.job_id)["status"])
        self.assertEqual([], self.executor_calls)

    def test_close_requests_cancellation_and_never_invents_completion(self):
        started = threading.Event()

        def blocking(_store, _package, **kwargs):
            kwargs["on_progress"](P10RuntimeCaptureV2Progress(0, 2, None, "running"))
            started.set()
            while not kwargs["is_cancelled"]():
                started.wait(0.01)
            raise P10RuntimeCaptureV2CommandError("cancelled")

        manager = self._manager(executor=blocking)
        submitted = manager.submit(self._payload("cancelled"))
        self.assertTrue(started.wait(3))
        manager.close()
        settled = manager.get(submitted["job_id"])
        self.assertEqual("interrupted_retryable", settled["status"])
        self.assertEqual("manager_closed", settled["failure_code"])
        self.assertNotIn("completed", [row["status"] for row in settled["events"]])

    def test_two_submissions_never_execute_concurrently(self):
        entered, release = threading.Event(), threading.Event()
        lock = threading.Lock()
        active = maximum = calls = 0

        def serialized(_store, _package, **kwargs):
            nonlocal active, maximum, calls
            with lock:
                active += 1
                calls += 1
                maximum = max(maximum, active)
                if calls == 1:
                    entered.set()
            if calls == 1:
                while not release.is_set() and not kwargs["is_cancelled"]():
                    release.wait(0.01)
            result = self._execute_success(_store, _package, **kwargs)
            with lock:
                active -= 1
            return result

        manager = self._manager(executor=serialized)
        first = manager.submit(self._payload("serial-1"))
        second = manager.submit(self._payload("serial-2"))
        self.assertTrue(entered.wait(3))
        self.assertEqual(1, calls)
        release.set()
        self.assertEqual("completed", manager.wait(first["job_id"], 5)["status"])
        self.assertEqual("completed", manager.wait(second["job_id"], 5)["status"])
        self.assertEqual(1, maximum)

    def _manager(
        self, *, environment=None, environment_loader=None,
        compiler=None, executor=None,
    ):
        selected = environment or self.environment
        manager = P10CaptureJobManager(
            self.projects,
            environment_loader=environment_loader or (lambda _root: selected),
            preview_compiler=compiler or self._compile,
            capture_executor=executor or self._execute_success,
        )
        self.managers.append(manager)
        return manager

    def _compile(self, _store, package_id):
        self.compiler_calls += 1
        self.assertEqual(SHA["package"], package_id)
        return self.preview

    def _execute_success(self, _store, package_id, **kwargs):
        self.assertEqual(SHA["package"], package_id)
        self.executor_calls.append((
            kwargs["expected_p10_1"], kwargs["expected_framing"],
            kwargs["license_acknowledged"], kwargs["run_confirmed"],
        ))
        for current in range(3):
            kwargs["on_progress"](P10RuntimeCaptureV2Progress(
                current, 2, None, "running",
            ))
        kwargs["on_progress"](P10RuntimeCaptureV2Progress(
            2, 2, None, "completed",
        ))
        return P10RuntimeCaptureV2CommandResult(
            package_id, "fixture-project", "idle", SHA["preview"],
            SHA["execution"], SHA["capture"], SHA["artifact"],
            SHA["bundle"], "google-chrome", "152.0.7977.64", 2, False,
        )

    def _preview(self, *, p10=None):
        inner = SimpleNamespace(document={
            "source": {"current_p10_1_head": dict(p10 or P10_HEAD)},
        })
        return P10PreviewV2CommandResult(
            SHA["package"], "fixture-project", "idle", SHA["preview"],
            SHA["preview_artifact"], SHA["frame_candidate"],
            SHA["frame_decision"], 2, 2, inner, self.workspace, self.state,
        )

    def _environment(self):
        runtime_root = self.state / "runtime-package"
        runtime = Spine42RuntimePackage(
            runtime_root, runtime_root / "player.js", runtime_root / "player.css",
            runtime_root / "LICENSE", b"js", b"css", "c" * 64, "d" * 64,
            "e" * 64, "f" * 64,
        )
        browser = BrowserExecutableSnapshot(
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "google-chrome", "152.0.7977.64", "0" * 64, "1" * 64, 4096,
        )
        return P10RuntimeEnvironment(runtime, browser)

    def _payload(self, client):
        return {
            "package_id": SHA["package"], "client_request_id": client,
            "expected_p10_1": dict(P10_HEAD),
            "expected_framing": dict(FRAMING),
            "explicit_runtime_license_confirmation": True,
            "explicit_run_confirmation": True,
        }

def caused(outer, inner):
    try:
        raise inner
    except BaseException as failure:
        try:
            raise outer from failure
        except BaseException as wrapped:
            return wrapped


if __name__ == "__main__":
    unittest.main()
