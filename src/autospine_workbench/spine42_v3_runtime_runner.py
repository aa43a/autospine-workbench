"""Trusted Windows runner for exact P10.7b official-runtime captures."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from urllib.parse import quote

from .body_sway_browser_profile_lease import (
    BodySwayBrowserProfileLease,
    BodySwayBrowserProfileLeaseError,
)
from .body_sway_capture_server_lease import (
    BodySwayCaptureServerLease,
    BodySwayCaptureServerLeaseError,
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
from .spine42_runtime_inputs import (
    Spine42RuntimeInputError,
    Spine42RuntimePackage,
    require_runtime_package,
)
from .spine42_v3_bundle_integrity import VerifiedSpine42V3Bundle
from .spine42_v3_bundle_reader import (
    VerifiedSpine42V3BundleReader,
    VerifiedSpine42V3BundleReaderError,
)
from .spine42_v3_headless_browser import (
    Spine42V3HeadlessBrowserError,
    run_spine42_v3_headless_capture,
)
from .spine42_v3_raster_metrics import (
    Spine42V3RasterMetricsError,
    compute_spine42_v3_raster_metrics,
)
from .spine42_v3_runtime_capture_collector import (
    Spine42V3RuntimeCaptureCollector,
    Spine42V3RuntimeCaptureCollectorError,
    Spine42V3RuntimeCaptureSnapshot,
)
from .spine42_v3_runtime_capture_server import (
    create_spine42_v3_runtime_capture_server,
)
from .spine42_v3_runtime_plan import (
    Spine42V3RuntimePlanError,
    build_spine42_v3_runtime_plan,
)
from .spine42_v3_runtime_session import (
    Spine42V3RuntimeSessionError,
    Spine42V3RuntimeSessions,
    build_spine42_v3_runtime_sessions,
)


class Spine42V3RuntimeRunnerError(RuntimeError):
    """Raised unless every official-runtime artifact is exact and complete."""


@dataclass(frozen=True, slots=True)
class Spine42V3RuntimeRun:
    """Private exact inputs and path-free identities from one completed run."""

    project_id: str
    clip_id: str
    skeleton_json_sha256: str
    spine42_v3_bundle_sha256: str
    capture_plan_sha256: str
    raster_metrics_sha256: str
    browser_family: str
    browser_reported_version: str
    artifact_count: int
    _bundle: VerifiedSpine42V3Bundle = field(repr=False)
    _runtime: Spine42RuntimePackage = field(repr=False)
    _browser: BrowserExecutableSnapshot = field(repr=False)
    _sessions: Spine42V3RuntimeSessions = field(repr=False)
    _snapshot: Spine42V3RuntimeCaptureSnapshot = field(repr=False)
    _metrics: dict = field(repr=False)

    @property
    def plan(self) -> dict:
        return self._sessions.plan

    @property
    def capture_bytes(self) -> dict[str, bytes]:
        return self._snapshot.capture_bytes

    @property
    def metrics(self) -> dict:
        return dict(self._metrics)

    @property
    def exact_inputs(self) -> tuple:
        """Return the frozen inputs consumed by the evidence compiler."""

        return (
            self._bundle, self._runtime, self._browser,
            self._sessions, self._snapshot,
        )


def run_spine42_v3_runtime_capture(
    state_root: Path,
    project_id: str,
    *,
    skeleton_json_sha256: str,
    spine42_v3_bundle_sha256: str,
    runtime_root: Path,
    browser_executable: Path,
    license_acknowledged: bool,
) -> Spine42V3RuntimeRun:
    """Replay one P10.7a address and capture every planned artifact."""

    if license_acknowledged is not True:
        raise Spine42V3RuntimeRunnerError(
            "Spine runtime license acknowledgement is required"
        )
    if os.name != "nt":
        raise Spine42V3RuntimeRunnerError(
            "Official runtime capture is supported only on Windows"
        )
    try:
        reader = VerifiedSpine42V3BundleReader(Path(state_root))
        bundle = reader.load(
            project_id, skeleton_json_sha256, spine42_v3_bundle_sha256
        )
        plan = build_spine42_v3_runtime_plan(bundle)
        runtime = require_runtime_package(Path(runtime_root))
        if not runtime.package_json_sha256 or not runtime.license_sha256:
            raise Spine42V3RuntimeRunnerError(
                "Runtime package and license snapshots are incomplete"
            )
        lease = LockedBrowserExecutableLease(browser_executable)
        with lease as browser:
            sessions = build_spine42_v3_runtime_sessions(
                bundle, runtime, plan
            )
            collector = Spine42V3RuntimeCaptureCollector(sessions)
            server = create_spine42_v3_runtime_capture_server(
                "127.0.0.1", 0, runtime, bundle, sessions, collector
            )
            with BodySwayCaptureServerLease(server) as server_lease:
                host, port = server.server_address[:2]
                _require_prefix(collector, ())
                for index, artifact_id in enumerate(collector.artifact_ids):
                    server_lease.require_healthy()
                    _require_prefix(
                        collector, collector.artifact_ids[:index]
                    )
                    recheck_browser_executable(browser)
                    with BodySwayBrowserProfileLease() as profile:
                        url = (
                            f"http://{host}:{port}/capture/"
                            f"{quote(artifact_id, safe='')}"
                        )
                        run_spine42_v3_headless_capture(
                            browser, url, profile, collector, artifact_id
                        )
                    _require_prefix(
                        collector, collector.artifact_ids[:index + 1]
                    )
                server_lease.require_healthy()
            recheck_browser_executable(browser)
            _require_same_bundle(
                bundle, reader.load(
                    project_id, skeleton_json_sha256,
                    spine42_v3_bundle_sha256,
                )
            )
            if require_runtime_package(Path(runtime_root)) != runtime:
                raise Spine42V3RuntimeRunnerError(
                    "Official runtime package changed during capture"
                )
            snapshot = collector.snapshot()
            metrics = compute_spine42_v3_raster_metrics(
                plan, snapshot.capture_bytes
            )
            result = _result(
                bundle, runtime, browser, sessions, snapshot, metrics
            )
        if not lease.closed:
            raise Spine42V3RuntimeRunnerError(
                "Browser executable lease did not close"
            )
        return result
    except Spine42V3RuntimeRunnerError:
        raise
    except _RUN_FAILURES as exc:
        raise Spine42V3RuntimeRunnerError(
            "Spine 4.2 v3 official-runtime capture failed"
        ) from exc


def _result(bundle, runtime, browser, sessions, snapshot, metrics):
    return Spine42V3RuntimeRun(
        bundle.project_id, bundle.clip_id, bundle.skeleton_json_sha256,
        bundle.bundle_sha256, sessions.plan["capture_plan_sha256"],
        metrics["raster_metrics_sha256"], browser.family,
        browser.reported_version, len(snapshot.capture_bytes), bundle,
        runtime, browser, sessions, snapshot, metrics,
    )


def _require_prefix(collector, expected) -> None:
    status = collector.status()
    if status != {
        "expected_artifact_ids": list(collector.artifact_ids),
        "captured_artifact_ids": list(expected),
        "error_artifact_ids": [],
        "complete": list(expected) == list(collector.artifact_ids),
    }:
        raise Spine42V3RuntimeRunnerError(
            "Collector differs from the exact completed prefix"
        )


def _require_same_bundle(before, after) -> None:
    if before.contract_identities != after.contract_identities \
            or before.document_bytes != after.document_bytes:
        raise Spine42V3RuntimeRunnerError(
            "Spine v3 bundle changed during official-runtime capture"
        )


_RUN_FAILURES = (
    BodySwayBrowserProfileLeaseError,
    BodySwayCaptureServerLeaseError,
    BrowserExecutableSnapshotError,
    LockedBrowserExecutableLeaseError,
    OSError,
    Spine42RuntimeInputError,
    Spine42V3HeadlessBrowserError,
    Spine42V3RasterMetricsError,
    Spine42V3RuntimeCaptureCollectorError,
    Spine42V3RuntimePlanError,
    Spine42V3RuntimeSessionError,
    TypeError,
    ValueError,
    VerifiedSpine42V3BundleReaderError,
)


__all__ = [
    "Spine42V3RuntimeRun", "Spine42V3RuntimeRunnerError",
    "run_spine42_v3_runtime_capture",
]
