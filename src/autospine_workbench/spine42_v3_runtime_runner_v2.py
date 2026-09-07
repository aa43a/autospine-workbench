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
from .spine42_v3_runtime_capture_server_v2 import (
    create_spine42_v3_runtime_capture_server_v2,
)
from .spine42_v3_runtime_run_document_v2 import build_spine42_v3_runtime_run_document_v2
from .spine42_v3_runtime_session_v2 import (
    Spine42V3RuntimeSessionV2Error, Spine42V3RuntimeSessionsV2,
    build_spine42_v3_runtime_sessions_v2,
)
from .spine42_v3_runtime_run_state_v2 import run_state
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


def _runtime_run_capability():
    issued, lock = WeakKeyDictionary(), threading.Lock()

    def issue(bundle, source, runtime, browser, sessions, snapshot):
        exact = (bundle, source, runtime, browser, sessions, snapshot)
        result = Spine42V3RuntimeRunV2(*_run_state(*exact))
        with lock:
            issued[result] = exact
        return result

    def require(value):
        """Return private exact inputs only for an unchanged issued run."""
        if type(value) is not Spine42V3RuntimeRunV2:
            raise Spine42V3RuntimeRunnerV2Error(
                "Runtime run v2 is not runner-issued"
            )
        with lock:
            exact = issued.get(value)
        types = (
            VerifiedSpine42V3BundleV2, VerifiedSpine42V3RuntimeSourceV2,
            Spine42RuntimePackage, BrowserExecutableSnapshot,
            Spine42V3RuntimeSessionsV2, Spine42V3RuntimeCaptureSnapshotV2,
        )
        if exact is None or len(exact) != len(types) or any(
            type(item) is not expected
            for item, expected in zip(exact or (), types, strict=True)
        ):
            raise Spine42V3RuntimeRunnerV2Error(
                "Runtime run v2 is not runner-issued"
            )
        expected = _run_state(*exact)
        actual = tuple(
            getattr(value, name) for name in value.__dataclass_fields__
        )
        if len(actual) != len(expected) or any(
            type(item) is not type(reference) or item != reference
            for item, reference in zip(actual, expected, strict=True)
        ):
            raise Spine42V3RuntimeRunnerV2Error(
                "Runner-issued runtime run v2 differs from exact inputs"
            )
        return exact

    def run(
        state_root: Path, project_id: str, *, skeleton_json_sha256: str,
        spine42_v3_bundle_sha256: str,
        expected_runtime: Spine42RuntimePackage,
        expected_browser: BrowserExecutableSnapshot,
        license_acknowledged: bool,
    ) -> Spine42V3RuntimeRunV2:
        """Read P10.7a once and capture under the exact authorization."""

        if license_acknowledged is not True:
            raise Spine42V3RuntimeRunnerV2Error(
                "Spine runtime license acknowledgement is required"
            )
        _require_windows()
        try:
            if type(expected_runtime) is not Spine42RuntimePackage \
                    or type(expected_browser) is not BrowserExecutableSnapshot:
                raise Spine42V3RuntimeRunnerV2Error(
                    "Authorized runtime environment is invalid"
                )
            state = Path(state_root)
            bundle = VerifiedSpine42V3BundleReaderV2(state).load(
                project_id, skeleton_json_sha256, spine42_v3_bundle_sha256,
            )
            source = VerifiedSpine42V3RuntimeSourceBridgeV2(
                state
            ).build_from_verified(bundle)
            runtime = require_runtime_package(expected_runtime.root)
            if runtime != expected_runtime or not runtime.package_json_sha256 \
                    or not runtime.license_sha256:
                raise Spine42V3RuntimeRunnerV2Error(
                    "Runtime package differs from the authorized snapshot"
                )
            lease = LockedBrowserExecutableLease(expected_browser.path)
            with lease as browser:
                if browser != expected_browser:
                    raise Spine42V3RuntimeRunnerV2Error(
                        "Browser differs from the authorized snapshot"
                    )
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
                    for index, artifact_id in enumerate(
                        collector.artifact_ids
                    ):
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
                if require_runtime_package(expected_runtime.root) != runtime:
                    raise Spine42V3RuntimeRunnerV2Error(
                        "Official runtime package changed during capture"
                    )
                snapshot = collector.snapshot()
                result = issue(
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

    return run, require


(
    run_spine42_v3_runtime_capture_v2,
    _require_issued_spine42_v3_runtime_run_v2,
) = _runtime_run_capability()


def _run_state(bundle, source, runtime, browser, sessions, snapshot):
    return run_state(
        bundle, source, runtime, browser, sessions, snapshot,
        Spine42V3RuntimeRunnerV2Error,
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
