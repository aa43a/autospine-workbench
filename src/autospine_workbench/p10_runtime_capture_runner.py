"""Trusted application service for complete P10 official-runtime captures."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from urllib.parse import quote

from .body_sway_browser_profile_lease import (
    BodySwayBrowserProfileLease,
    BodySwayBrowserProfileLeaseError,
)
from .body_sway_headless_browser import (
    BodySwayHeadlessBrowserError,
    run_body_sway_headless_capture_case,
)
from .body_sway_runtime_capture import (
    BodySwayRuntimeCapture,
    BodySwayRuntimeCaptureError,
    compile_body_sway_runtime_capture,
    require_exact_body_sway_runtime_capture,
)
from .body_sway_runtime_capture_collector import (
    BodySwayRuntimeCaptureCollectorError,
)
from .body_sway_capture_server_lease import (
    BodySwayCaptureServerLease,
    BodySwayCaptureServerLeaseError,
)
from .body_sway_runtime_capture_harness import (
    build_body_sway_runtime_capture_harness,
)
from .body_sway_runtime_capture_session import (
    BodySwayRuntimeCaptureSessionError,
)
from .browser_executable_snapshot import (
    BrowserExecutableSnapshotError,
    recheck_browser_executable,
)
from .locked_browser_executable_lease import (
    LockedBrowserExecutableLease,
    LockedBrowserExecutableLeaseError,
)
from .p10_preview_commands import (
    P10PreviewCommandError,
    P10PreviewCommandResult,
    require_exact_preview_for_mount,
)
from .spine42_runtime_inputs import (
    Spine42RuntimeInputError,
    Spine42RuntimePackage,
    require_runtime_package,
)


class P10RuntimeCaptureRunnerError(RuntimeError):
    """Raised unless every fixed case yields trusted official-runtime bytes."""


@dataclass(frozen=True, slots=True)
class P10RuntimeCaptureResult:
    """Frozen public identities plus privately held manifest and PNG bytes."""

    temporary_preview_sha256: str
    runtime_capture_sha256: str
    artifact_set_sha256: str
    browser_family: str
    browser_reported_version: str
    case_count: int
    _capture: BodySwayRuntimeCapture = field(repr=False)

    @property
    def document(self) -> dict:
        return self._capture.document

    @property
    def capture_bytes(self) -> dict[str, bytes]:
        return self._capture.capture_bytes


def run_p10_body_sway_runtime_capture(
    preview_result: P10PreviewCommandResult,
    *,
    runtime_root: Path,
    browser_executable: Path,
    license_acknowledged: bool,
) -> P10RuntimeCaptureResult:
    """Replay, mount, capture every case, and compile unreviewed evidence."""

    if license_acknowledged is not True:
        raise P10RuntimeCaptureRunnerError(
            "Spine runtime license acknowledgement is required before capture"
        )
    if type(preview_result) is not P10PreviewCommandResult:
        raise P10RuntimeCaptureRunnerError(
            "Runtime capture requires an exact P10 preview command result"
        )
    if os.name != "nt":
        raise P10RuntimeCaptureRunnerError(
            "P10 runtime capture is supported only on Windows"
        )
    try:
        browser_lease = LockedBrowserExecutableLease(browser_executable)
        with browser_lease as browser:
            preview = require_exact_preview_for_mount(preview_result)
            runtime = require_runtime_package(Path(runtime_root))
            harness = build_body_sway_runtime_capture_harness(preview, runtime)
            case_ids = harness.collector.case_ids
            with BodySwayCaptureServerLease(harness.server) as server_lease:
                host, port = harness.server.server_address[:2]
                _require_exact_collector_prefix(harness.collector, ())
                for index, case_id in enumerate(case_ids):
                    server_lease.require_healthy()
                    _require_exact_collector_prefix(
                        harness.collector, case_ids[:index]
                    )
                    recheck_browser_executable(browser)
                    with BodySwayBrowserProfileLease() as profile_path:
                        url = (
                            f"http://{host}:{port}/capture/"
                            f"{quote(case_id, safe='')}"
                        )
                        run_body_sway_headless_capture_case(
                            browser,
                            url,
                            profile_path,
                            harness.collector,
                            case_id,
                        )
                    server_lease.require_healthy()
                    _require_exact_collector_prefix(
                        harness.collector, case_ids[:index + 1]
                    )
                server_lease.require_healthy()
            recheck_browser_executable(browser)
            _require_same_preview(
                preview, require_exact_preview_for_mount(preview_result)
            )
            _require_same_runtime(
                runtime, require_runtime_package(Path(runtime_root))
            )
            snapshot = harness.collector.snapshot()
            capture = compile_body_sway_runtime_capture(
                preview, runtime, harness.sessions, snapshot, browser
            )
            replay_sha = require_exact_body_sway_runtime_capture(
                preview, runtime, harness.sessions, snapshot, browser,
                capture.document, capture.capture_bytes,
            )
            if replay_sha != capture.sha256:
                raise P10RuntimeCaptureRunnerError(
                    "Runtime capture identity changed during exact replay"
                )
            result = P10RuntimeCaptureResult(
                temporary_preview_sha256=preview.sha256,
                runtime_capture_sha256=capture.sha256,
                artifact_set_sha256=capture.artifact_set_sha256,
                browser_family=browser.family,
                browser_reported_version=browser.reported_version,
                case_count=len(capture.document["cases"]),
                _capture=capture,
            )
        if not browser_lease.closed:
            raise P10RuntimeCaptureRunnerError(
                "Browser executable lease did not close after exact replay"
            )
        return result
    except P10RuntimeCaptureRunnerError:
        raise
    except _ERRORS as exc:
        raise P10RuntimeCaptureRunnerError(
            f"Body-sway runtime capture failed: {exc}"
        ) from exc


def _require_exact_collector_prefix(collector, expected) -> None:
    try:
        status = collector.status()
        if type(status) is not dict \
                or set(status) != {
                    "expected_case_ids", "captured_case_ids",
                    "error_case_ids", "complete",
                } \
                or status.get("expected_case_ids") != list(collector.case_ids) \
                or status.get("captured_case_ids") != list(expected) \
                or status.get("error_case_ids") != [] \
                or status.get("complete") is not (
                    list(expected) == list(collector.case_ids)
                ):
            raise P10RuntimeCaptureRunnerError(
                "Browser exited without the exact collector capture; "
                "state differs from the exact completed prefix"
            )
    except P10RuntimeCaptureRunnerError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise P10RuntimeCaptureRunnerError(
            "Collector state cannot be verified"
        ) from exc


def _require_same_preview(before, after) -> None:
    if before.canonical_bytes != after.canonical_bytes \
            or before.artifact_bytes != after.artifact_bytes:
        raise P10RuntimeCaptureRunnerError(
            "Persisted preview inputs changed during runtime capture"
        )


def _require_same_runtime(
    before: Spine42RuntimePackage, after: Spine42RuntimePackage,
) -> None:
    if before != after:
        raise P10RuntimeCaptureRunnerError(
            "Official runtime package changed during capture"
        )


_ERRORS = (
    BodySwayBrowserProfileLeaseError,
    BodySwayHeadlessBrowserError,
    BodySwayCaptureServerLeaseError,
    BodySwayRuntimeCaptureCollectorError,
    BodySwayRuntimeCaptureError,
    BodySwayRuntimeCaptureSessionError,
    BrowserExecutableSnapshotError,
    LockedBrowserExecutableLeaseError,
    OSError,
    P10PreviewCommandError,
    Spine42RuntimeInputError,
    TypeError,
    ValueError,
)
