"""Small fake leases and assertions shared by runtime runner tests."""

from pathlib import Path
from autospine_workbench.body_sway_capture_server_lease import (
    BodySwayCaptureServerLeaseError,
    BodySwayCaptureServerLease as RealServerLease,
)


class _BrowserLease:
    def __init__(self, browser):
        self.browser = browser
        self.active = False
        self.closed = False

    def __enter__(self):
        self.active = True
        return self.browser

    def __exit__(self, kind, value, traceback):
        self.active = False
        self.closed = True


class _ServerLease:
    def __init__(self, server, *, fail_at=None):
        self.delegate = RealServerLease(server)
        self.health_checks = 0
        self.closed = False
        self.fail_at = fail_at

    def __enter__(self):
        self.delegate.__enter__()
        return self

    def require_healthy(self):
        self.health_checks += 1
        if self.health_checks == self.fail_at:
            raise BodySwayCaptureServerLeaseError("injected unhealthy")
        self.delegate.require_healthy()

    def __exit__(self, kind, value, traceback):
        try:
            return self.delegate.__exit__(kind, value, traceback)
        finally:
            self.closed = True


def _capture(collector, artifact_id, png):
    observed = collector.session(artifact_id)["expected_observables"]
    collector.record_capture(
        artifact_id, png, device_pixel_ratio=1,
        observed_inventory=observed,
    )


def _assert_path_free(test, value, forbidden):
    if isinstance(value, Path):
        test.fail(f"Path leaked into detached result: {value}")
    if isinstance(value, str):
        test.assertNotIn(forbidden, value)
    elif isinstance(value, dict):
        for key, item in value.items():
            _assert_path_free(test, key, forbidden)
            _assert_path_free(test, item, forbidden)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _assert_path_free(test, item, forbidden)
