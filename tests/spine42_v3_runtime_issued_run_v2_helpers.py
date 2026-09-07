"""Issue v2 runner results through mocked I/O boundaries, never a real Runtime."""

from __future__ import annotations

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch

import autospine_workbench.spine42_v3_runtime_runner_v2 as subject


def issued_runtime_run_v2(fixture, runtime, browser, png):
    """Exercise the public runner while replacing every external boundary."""

    reader, bridge = Mock(), Mock()
    reader.load.return_value = fixture.bundle
    bridge.build_from_verified.return_value = fixture.source
    browser_lease = _BrowserLease(browser)

    def capture(_browser, _url, _profile, collector, artifact_id):
        observed = collector.session(artifact_id)["expected_observables"]
        collector.record_capture(
            artifact_id, png, device_pixel_ratio=1,
            observed_inventory=observed,
        )

    boundaries = (
        patch.object(subject, "_require_windows"),
        patch.object(
            subject, "VerifiedSpine42V3BundleReaderV2",
            return_value=reader,
        ),
        patch.object(
            subject, "VerifiedSpine42V3RuntimeSourceBridgeV2",
            return_value=bridge,
        ),
        patch.object(
            subject, "require_runtime_package",
            side_effect=[runtime, runtime],
        ),
        patch.object(
            subject, "LockedBrowserExecutableLease",
            return_value=browser_lease,
        ),
        patch.object(
            subject, "recheck_browser_executable", return_value=browser,
        ),
        patch.object(
            subject, "create_spine42_v3_runtime_capture_server_v2",
            return_value=SimpleNamespace(
                server_address=("127.0.0.1", 12345),
            ),
        ),
        patch.object(
            subject, "BodySwayCaptureServerLease",
            side_effect=lambda server: _ServerLease(server),
        ),
        patch.object(
            subject, "run_spine42_v3_headless_capture_v2",
            side_effect=capture,
        ),
    )
    with ExitStack() as stack:
        for boundary in boundaries:
            stack.enter_context(boundary)
        bundle = fixture.bundle
        return subject.run_spine42_v3_runtime_capture_v2(
            fixture.source_fixture.state_root, bundle.project_id,
            skeleton_json_sha256=bundle.skeleton_json_sha256,
            spine42_v3_bundle_sha256=bundle.bundle_sha256,
            expected_runtime=runtime, expected_browser=browser,
            license_acknowledged=True,
        )


class _BrowserLease:
    def __init__(self, browser):
        self.browser, self.closed = browser, False

    def __enter__(self):
        return self.browser

    def __exit__(self, _kind, _value, _traceback):
        self.closed = True


class _ServerLease:
    def __init__(self, server):
        self.server = server

    def __enter__(self):
        return self

    def require_healthy(self):
        return None

    def __exit__(self, _kind, _value, _traceback):
        return None


__all__ = ["issued_runtime_run_v2"]
