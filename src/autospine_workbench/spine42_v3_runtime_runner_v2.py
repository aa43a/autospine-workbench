"""Trusted Windows runner for exact P10.7b v2 runtime captures."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import threading
from urllib.parse import quote
from weakref import WeakKeyDictionary

from .body_sway_browser_profile_lease import (
    BodySwayBrowserProfileLease, BodySwayBrowserProfileLeaseError,
)
from .body_sway_capture_server_lease import (
    BodySwayCaptureServerLease, BodySwayCaptureServerLeaseError,
)
from .browser_executable_snapshot import (
    BrowserExecutableSnapshot, BrowserExecutableSnapshotError,
    recheck_browser_executable,
)
from .locked_browser_executable_lease import (
    LockedBrowserExecutableLease, LockedBrowserExecutableLeaseError,
)
from .spine42_runtime_inputs import (
    Spine42RuntimeInputError, Spine42RuntimePackage,
    require_runtime_package,
)
from .spine42_v3_bundle_reader_v2 import (
    VerifiedSpine42V3BundleReaderV2, VerifiedSpine42V3BundleReaderV2Error,
    VerifiedSpine42V3BundleV2,
)
from .spine42_v3_headless_browser_v2 import (
    Spine42V3HeadlessBrowserV2Error,
    run_spine42_v3_headless_capture_v2,
)
from .spine42_v3_runtime_capture_collector_v2 import (
    Spine42V3RuntimeCaptureCollectorV2,
    Spine42V3RuntimeCaptureCollectorV2Error,
    Spine42V3RuntimeCaptureSnapshotV2,
)
from .spine42_v3_runtime_capture_report import require_capture_snapshot_consistency
from .spine42_v3_runtime_capture_server_v2 import (
    create_spine42_v3_runtime_capture_server_v2,
)
from .spine42_v3_runtime_run_document_v2 import build_spine42_v3_runtime_run_document_v2
from .spine42_v3_runtime_session_v2 import (
    Spine42V3RuntimeSessionV2Error, Spine42V3RuntimeSessionsV2,
    build_spine42_v3_runtime_sessions_v2,
    require_exact_spine42_v3_runtime_sessions_v2,
)
from .spine42_v3_runtime_session_core import canonical_json
from .spine42_v3_runtime_source_bridge_v2 import (
    Spine42V3RuntimeSourceBridgeV2Error, VerifiedSpine42V3RuntimeSourceBridgeV2,
    VerifiedSpine42V3RuntimeSourceV2,
)


class Spine42V3RuntimeRunnerV2Error(RuntimeError):
    """Raised unless every v2 runtime artifact is exact and complete."""


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class Spine42V3RuntimeRunV2:
    """Path-free detached result; exact inputs remain issuer-private."""

    project_id: str
    clip_id: str
    skeleton_json_sha256: str
    spine42_v3_bundle_sha256: str
    source_admission_sha256: str
    capture_plan_sha256: str
    session_set_sha256: str
    runtime_package_json_sha256: str
    runtime_license_sha256: str
    browser_family: str
    browser_reported_version: str
    browser_version_output_sha256: str
    browser_executable_sha256: str
    browser_executable_size_bytes: int
    artifact_count: int
    license_acknowledged: bool
    _plan_json: str = field(repr=False)
    _admission_json: str = field(repr=False)
    _reports_json: str = field(repr=False)
    _capture_items: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def plan(self) -> dict:
        return json.loads(self._plan_json)

    @property
    def source_admission(self) -> dict:
        return json.loads(self._admission_json)

    @property
    def reports(self) -> tuple[dict, ...]:
        return tuple(json.loads(self._reports_json))

    @property
    def capture_bytes(self) -> dict[str, bytes]:
        return dict(self._capture_items)

    @property
    def document(self) -> dict:
        return build_spine42_v3_runtime_run_document_v2(self)


_ISSUED_RUN_INPUTS = WeakKeyDictionary()
_ISSUED_RUN_LOCK = threading.Lock()


def run_spine42_v3_runtime_capture_v2(
    state_root: Path,
    project_id: str,
    *,
    skeleton_json_sha256: str,
    spine42_v3_bundle_sha256: str,
    runtime_root: Path,
    browser_executable: Path,
    license_acknowledged: bool,
) -> Spine42V3RuntimeRunV2:
    """Read P10.7a v2 once and collect every runtime artifact in memory."""

    if license_acknowledged is not True:
        raise Spine42V3RuntimeRunnerV2Error(
            "Spine runtime license acknowledgement is required"
        )
    _require_windows()
    try:
        state = Path(state_root)
        bundle = VerifiedSpine42V3BundleReaderV2(state).load(
            project_id, skeleton_json_sha256, spine42_v3_bundle_sha256,
        )
        source = VerifiedSpine42V3RuntimeSourceBridgeV2(
            state
        ).build_from_verified(bundle)
        runtime = require_runtime_package(Path(runtime_root))
        if not runtime.package_json_sha256 or not runtime.license_sha256:
            raise Spine42V3RuntimeRunnerV2Error(
                "Runtime package and license snapshots are incomplete"
            )
        lease = LockedBrowserExecutableLease(browser_executable)
        with lease as browser:
            sessions = build_spine42_v3_runtime_sessions_v2(
                bundle, runtime, source,
            )
            collector = Spine42V3RuntimeCaptureCollectorV2(sessions)
            server = create_spine42_v3_runtime_capture_server_v2(
                "127.0.0.1", 0, runtime, bundle, source,
                sessions, collector,
            )
            with BodySwayCaptureServerLease(server) as server_lease:
                host, port = server.server_address[:2]
                _require_prefix(collector, ())
                for index, artifact_id in enumerate(collector.artifact_ids):
                    server_lease.require_healthy()
                    _require_prefix(
                        collector, collector.artifact_ids[:index],
                    )
                    recheck_browser_executable(browser)
                    with BodySwayBrowserProfileLease() as profile:
                        url = (
                            f"http://{host}:{port}/capture/"
                            f"{quote(artifact_id, safe='')}"
                        )
                        run_spine42_v3_headless_capture_v2(
                            browser, url, profile, collector, artifact_id,
                        )
                    _require_prefix(
                        collector, collector.artifact_ids[:index + 1],
                    )
                server_lease.require_healthy()
            recheck_browser_executable(browser)
            if require_runtime_package(Path(runtime_root)) != runtime:
                raise Spine42V3RuntimeRunnerV2Error(
                    "Official runtime package changed during capture"
                )
            snapshot = collector.snapshot()
            result = _result(
                bundle, source, runtime, browser, sessions, snapshot,
            )
        if not lease.closed:
            raise Spine42V3RuntimeRunnerV2Error(
                "Browser executable lease did not close"
            )
        return result
    except Spine42V3RuntimeRunnerV2Error:
        raise
    except _RUN_FAILURES as exc:
        raise Spine42V3RuntimeRunnerV2Error(
            "Spine 4.2 v3 official-runtime capture v2 failed"
        ) from exc


def _result(bundle, source, runtime, browser, sessions, snapshot):
    exact = (bundle, source, runtime, browser, sessions, snapshot)
    result = Spine42V3RuntimeRunV2(*_run_state(*exact))
    with _ISSUED_RUN_LOCK:
        _ISSUED_RUN_INPUTS[result] = exact
    return result


def _require_issued_spine42_v3_runtime_run_v2(value) -> tuple:
    """Return private exact inputs only for an unchanged runner-issued run."""
    if type(value) is not Spine42V3RuntimeRunV2:
        raise Spine42V3RuntimeRunnerV2Error(
            "Runtime run v2 is not runner-issued"
        )
    with _ISSUED_RUN_LOCK:
        exact = _ISSUED_RUN_INPUTS.get(value)
    if exact is None:
        raise Spine42V3RuntimeRunnerV2Error(
            "Runtime run v2 is not runner-issued"
        )
    types = (
        VerifiedSpine42V3BundleV2, VerifiedSpine42V3RuntimeSourceV2,
        Spine42RuntimePackage, BrowserExecutableSnapshot,
        Spine42V3RuntimeSessionsV2, Spine42V3RuntimeCaptureSnapshotV2,
    )
    if len(exact) != len(types) or any(
        type(item) is not expected
        for item, expected in zip(exact, types, strict=True)
    ):
        raise Spine42V3RuntimeRunnerV2Error(
            "Runner-issued runtime run v2 exact inputs are invalid"
        )
    expected = _run_state(*exact)
    actual = tuple(getattr(value, name) for name in value.__dataclass_fields__)
    if len(actual) != len(expected) or any(
        type(item) is not type(reference) or item != reference
        for item, reference in zip(actual, expected, strict=True)
    ):
        raise Spine42V3RuntimeRunnerV2Error(
            "Runner-issued runtime run v2 differs from exact inputs"
        )
    return exact


def _run_state(bundle, source, runtime, browser, sessions, snapshot):
    require_exact_spine42_v3_runtime_sessions_v2(
        bundle, runtime, source, sessions,
    )
    captures, reports = snapshot.capture_bytes, snapshot.reports
    artifact_ids = sessions.artifact_ids
    if tuple(captures) != artifact_ids or len(reports) != len(artifact_ids):
        raise Spine42V3RuntimeRunnerV2Error("Runtime snapshot order is invalid")
    require_capture_snapshot_consistency(
        artifact_ids, sessions.session_bytes, captures,
        dict(zip(artifact_ids, reports, strict=True)),
        error_type=Spine42V3RuntimeRunnerV2Error,
    )
    return (
        bundle.project_id, bundle.clip_id, bundle.skeleton_json_sha256,
        bundle.bundle_sha256, source.admission_sha256,
        source.capture_plan_sha256, sessions.sha256,
        runtime.package_json_sha256, runtime.license_sha256,
        browser.family, browser.reported_version,
        browser.version_output_sha256, browser.executable_sha256,
        browser.size_bytes, len(captures), True,
        canonical_json(sessions.plan), canonical_json(sessions.source_admission),
        canonical_json(list(reports)), tuple(captures.items()),
    )


def _require_windows() -> None:
    if os.name != "nt":
        raise Spine42V3RuntimeRunnerV2Error(
            "Official runtime capture v2 is supported only on Windows"
        )


def _require_prefix(collector, expected) -> None:
    status = collector.status()
    if status != {
        "expected_artifact_ids": list(collector.artifact_ids),
        "captured_artifact_ids": list(expected),
        "error_artifact_ids": [],
        "complete": list(expected) == list(collector.artifact_ids),
    }:
        raise Spine42V3RuntimeRunnerV2Error(
            "Collector differs from the exact completed prefix"
        )


_RUN_FAILURES = (
    BodySwayBrowserProfileLeaseError, BodySwayCaptureServerLeaseError,
    BrowserExecutableSnapshotError, LockedBrowserExecutableLeaseError,
    OSError, Spine42RuntimeInputError, Spine42V3HeadlessBrowserV2Error,
    Spine42V3RuntimeCaptureCollectorV2Error,
    Spine42V3RuntimeSessionV2Error,
    Spine42V3RuntimeSourceBridgeV2Error, TypeError, ValueError,
    VerifiedSpine42V3BundleReaderV2Error,
)

__all__ = [
    "Spine42V3RuntimeRunV2", "Spine42V3RuntimeRunnerV2Error",
    "run_spine42_v3_runtime_capture_v2",
]
