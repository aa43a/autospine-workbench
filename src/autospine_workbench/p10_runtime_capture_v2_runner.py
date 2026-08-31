"""Trusted runner for one confirmed package-centric Preview v2 capture."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from .body_sway_browser_profile_lease import (
    BodySwayBrowserProfileLease,
    BodySwayBrowserProfileLeaseError,
)
from .body_sway_capture_server_lease import (
    BodySwayCaptureServerLease,
    BodySwayCaptureServerLeaseError,
)
from .body_sway_headless_browser_v2 import (
    BodySwayHeadlessBrowserError,
    run_body_sway_headless_capture_case,
)
from .body_sway_runtime_capture_collector import (
    BodySwayRuntimeCaptureCollectorError,
)
from .body_sway_runtime_capture_harness_v2 import (
    build_body_sway_runtime_capture_harness_v2,
)
from .body_sway_runtime_capture_session_v2 import (
    BodySwayRuntimeCaptureSessionV2Error,
)
from .body_sway_runtime_capture_v2_compiler import (
    BodySwayRuntimeCaptureV2CompilerError,
    compile_body_sway_runtime_capture_v2,
    require_exact_body_sway_runtime_capture_v2,
)
from .body_sway_runtime_execution import (
    BodySwayRuntimeExecution,
    BodySwayRuntimeExecutionError,
    compile_body_sway_runtime_execution,
    require_exact_body_sway_runtime_execution,
)
from .browser_executable_snapshot import (
    BrowserExecutableSnapshot,
    BrowserExecutableSnapshotError,
    recheck_browser_executable,
)
from .locked_browser_executable_lease import (
    LockedBrowserExecutableLease,
    LockedBrowserExecutableLeaseError,
)
from .p10_preview_v2_commands import (
    P10PreviewV2CommandError,
    P10PreviewV2CommandResult,
    require_exact_preview_v2_for_mount,
)
from .p10_runtime_environment import P10RuntimeEnvironment
from .spine42_runtime_inputs import (
    Spine42RuntimeInputError,
    Spine42RuntimePackage,
    require_runtime_package,
)


class P10RuntimeCaptureV2RunnerError(RuntimeError):
    """Raised unless every fixed case yields exact official-runtime evidence."""

@dataclass(frozen=True, slots=True)
class P10RuntimeCaptureV2Progress:
    completed_case_count: int
    total_case_count: int
    current_case_id: str | None
    state: str

@dataclass(frozen=True, slots=True)
class P10RuntimeCaptureV2Result:
    package_id: str
    project_id: str
    clip_id: str
    temporary_preview_v2_sha256: str
    runtime_execution_sha256: str
    runtime_capture_v2_sha256: str
    artifact_set_sha256: str
    browser_family: str
    browser_reported_version: str
    case_count: int
    _execution: BodySwayRuntimeExecution = field(repr=False)

    @property
    def execution(self) -> BodySwayRuntimeExecution:
        return self._execution

def run_p10_body_sway_runtime_capture_v2(
    preview_result: P10PreviewV2CommandResult,
    *,
    environment: P10RuntimeEnvironment,
    license_acknowledged: bool,
    run_confirmed: bool,
    on_progress: Callable[[P10RuntimeCaptureV2Progress], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> P10RuntimeCaptureV2Result:
    """Replay, execute every case, and compile one unreviewed outer receipt."""

    _require_authority(license_acknowledged, run_confirmed)
    if type(preview_result) is not P10PreviewV2CommandResult:
        raise P10RuntimeCaptureV2RunnerError(
            "Runtime capture v2 requires an exact Preview v2 command result"
        )
    runtime_expected, browser_expected = _environment(environment)
    if os.name != "nt":
        raise P10RuntimeCaptureV2RunnerError(
            "P10 runtime capture v2 is supported only on Windows"
        )
    try:
        lease = LockedBrowserExecutableLease(Path(browser_expected.path))
        with lease as browser:
            if browser != browser_expected:
                raise P10RuntimeCaptureV2RunnerError(
                    "Detected browser changed before capture"
                )
            preview = require_exact_preview_v2_for_mount(preview_result)
            runtime = require_runtime_package(runtime_expected.root)
            _require_same_runtime(runtime_expected, runtime)
            harness = build_body_sway_runtime_capture_harness_v2(
                preview, runtime,
            )
            case_ids = harness.collector.case_ids
            _emit(on_progress, 0, len(case_ids), None, "running")
            with BodySwayCaptureServerLease(harness.server) as server_lease:
                host, port = harness.server.server_address[:2]
                _require_exact_collector_prefix(harness.collector, ())
                for index, case_id in enumerate(case_ids):
                    _require_not_cancelled(is_cancelled)
                    server_lease.require_healthy()
                    _require_exact_collector_prefix(
                        harness.collector, case_ids[:index],
                    )
                    recheck_browser_executable(browser)
                    with BodySwayBrowserProfileLease() as profile_path:
                        url = (
                            f"http://{host}:{port}/capture/"
                            f"{quote(case_id, safe='')}"
                        )
                        run_body_sway_headless_capture_case(
                            browser, url, profile_path,
                            harness.collector, case_id,
                        )
                    server_lease.require_healthy()
                    _require_exact_collector_prefix(
                        harness.collector, case_ids[:index + 1],
                    )
                    _emit(
                        on_progress, index + 1, len(case_ids),
                        case_id, "running",
                    )
                server_lease.require_healthy()
            _require_not_cancelled(is_cancelled)
            recheck_browser_executable(browser)
            replayed_preview = require_exact_preview_v2_for_mount(
                preview_result,
            )
            _require_same_preview(preview, replayed_preview)
            _require_same_runtime(
                runtime, require_runtime_package(runtime_expected.root),
            )
            snapshot = harness.collector.snapshot()
            capture = compile_body_sway_runtime_capture_v2(
                preview, runtime, harness.sessions, snapshot, browser,
            )
            capture_sha = require_exact_body_sway_runtime_capture_v2(
                preview, runtime, harness.sessions, snapshot, browser, capture,
            )
            if capture_sha != capture.sha256:
                raise P10RuntimeCaptureV2RunnerError(
                    "Runtime capture v2 identity changed during exact replay"
                )
            execution = compile_body_sway_runtime_execution(
                preview, runtime, harness.sessions, snapshot, browser, capture,
                license_acknowledged=True,
            )
            execution_sha = require_exact_body_sway_runtime_execution(
                preview, runtime, harness.sessions, snapshot,
                browser, execution,
            )
            if execution_sha != execution.sha256:
                raise P10RuntimeCaptureV2RunnerError(
                    "Runtime execution identity changed during exact replay"
                )
            result = _result(preview_result, browser, execution)
            _emit(on_progress, len(case_ids), len(case_ids), None, "completed")
        if not lease.closed:
            raise P10RuntimeCaptureV2RunnerError(
                "Browser executable lease did not close after exact replay"
            )
        return result
    except P10RuntimeCaptureV2RunnerError:
        raise
    except _ERRORS as exc:
        raise P10RuntimeCaptureV2RunnerError(
            f"Body-sway runtime capture v2 failed: {exc}"
        ) from exc

def _require_authority(license_acknowledged, run_confirmed):
    if license_acknowledged is not True:
        raise P10RuntimeCaptureV2RunnerError(
            "Explicit Spine runtime license acknowledgement is required"
        )
    if run_confirmed is not True:
        raise P10RuntimeCaptureV2RunnerError(
            "Explicit official runtime execution confirmation is required"
        )


def _environment(value):
    if type(value) is not P10RuntimeEnvironment \
            or type(value.runtime) is not Spine42RuntimePackage \
            or type(value.browser) is not BrowserExecutableSnapshot:
        raise P10RuntimeCaptureV2RunnerError(
            "The pinned runtime and browser environment is unavailable"
        )
    return value.runtime, value.browser


def _require_exact_collector_prefix(collector, expected) -> None:
    status = collector.status()
    exact = {
        "expected_case_ids", "captured_case_ids", "error_case_ids", "complete",
    }
    if type(status) is not dict or set(status) != exact \
            or status.get("expected_case_ids") != list(collector.case_ids) \
            or status.get("captured_case_ids") != list(expected) \
            or status.get("error_case_ids") != [] \
            or status.get("complete") is not (
                list(expected) == list(collector.case_ids)
            ):
        raise P10RuntimeCaptureV2RunnerError(
            "Browser exited without the exact completed collector prefix"
        )


def _require_same_preview(before, after) -> None:
    if before.canonical_bytes != after.canonical_bytes \
            or before.artifact_bytes != after.artifact_bytes:
        raise P10RuntimeCaptureV2RunnerError(
            "Persisted Preview v2 inputs changed during runtime capture"
        )


def _require_same_runtime(before, after) -> None:
    if before != after:
        raise P10RuntimeCaptureV2RunnerError(
            "Official runtime package changed during capture"
        )


def _require_not_cancelled(callback) -> None:
    if callback is not None and callback() is True:
        raise P10RuntimeCaptureV2RunnerError("Runtime capture was cancelled")


def _emit(callback, completed, total, case_id, state) -> None:
    if callback is not None:
        callback(P10RuntimeCaptureV2Progress(completed, total, case_id, state))


def _result(preview_result, browser, execution):
    source = execution.document["source"]
    return P10RuntimeCaptureV2Result(
        preview_result.package_id,
        execution.document["project_id"],
        execution.document["clip_id"],
        source["temporary_preview_v2_sha256"],
        execution.sha256,
        source["runtime_capture_v2_sha256"],
        execution.artifact_set_sha256,
        browser.family,
        browser.reported_version,
        execution.document["summary"]["case_count"],
        execution,
    )


_ERRORS = (
    BodySwayBrowserProfileLeaseError, BodySwayCaptureServerLeaseError,
    BodySwayHeadlessBrowserError, BodySwayRuntimeCaptureCollectorError,
    BodySwayRuntimeCaptureSessionV2Error,
    BodySwayRuntimeCaptureV2CompilerError, BodySwayRuntimeExecutionError,
    BrowserExecutableSnapshotError, LockedBrowserExecutableLeaseError,
    OSError, P10PreviewV2CommandError, RuntimeError,
    Spine42RuntimeInputError, TypeError, ValueError,
)


__all__ = [
    "P10RuntimeCaptureV2Progress", "P10RuntimeCaptureV2Result",
    "P10RuntimeCaptureV2RunnerError",
    "run_p10_body_sway_runtime_capture_v2",
]
