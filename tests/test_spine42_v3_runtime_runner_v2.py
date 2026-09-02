"""Trusted orchestration tests for the P10.7b v2 browser runner."""

from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

import autospine_workbench.spine42_v3_runtime_runner_v2 as subject  # noqa: E402
from autospine_workbench.browser_executable_snapshot import (  # noqa: E402
    BrowserExecutableSnapshot, BrowserExecutableSnapshotError,
)
from autospine_workbench.browser_version_identity import (  # noqa: E402
    browser_version_identity_sha256,
)
from autospine_workbench.body_sway_capture_server_lease import (  # noqa: E402
    BodySwayCaptureServerLeaseError,
    BodySwayCaptureServerLease as RealServerLease,
)
from autospine_workbench.spine42_v3_bundle_reader_v2 import (  # noqa: E402
    VerifiedSpine42V3BundleV2,
)
from autospine_workbench.spine42_v3_runtime_capture_collector_v2 import (  # noqa: E402
    Spine42V3RuntimeCaptureSnapshotV2,
)
from autospine_workbench.spine42_v3_runtime_runner_v2 import (  # noqa: E402
    Spine42V3RuntimeRunnerV2Error,
    run_spine42_v3_runtime_capture_v2,
)
from autospine_workbench.spine42_v3_runtime_session_v2 import (  # noqa: E402
    Spine42V3RuntimeSessionsV2,
)
from autospine_workbench.spine42_v3_runtime_source_bridge_v2 import (  # noqa: E402
    VerifiedSpine42V3RuntimeSourceV2,
)
from tests.test_spine42_v3_runtime_capture_harness import _png  # noqa: E402
from tests.test_spine42_v3_runtime_capture_harness_v2 import (  # noqa: E402
    V2HarnessFixture, _fake_runtime_profile_v2,
)


class Spine42V3RuntimeRunnerV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.fixture = V2HarnessFixture(cls.root / "fixture")
        cls.runtime = replace(
            cls.fixture.runtime,
            package_json_sha256="a" * 64, license_sha256="b" * 64,
        )
        version = "128.0.6613.0"
        cls.browser = BrowserExecutableSnapshot(
            path=str(cls.root / "chrome.exe"), family="chromium",
            reported_version=version,
            version_output_sha256=browser_version_identity_sha256(
                "chromium", version,
            ),
            executable_sha256="c" * 64, size_bytes=4096,
        )
        cls.png = _png()

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_one_exact_read_captures_complete_ordered_path_free_result(self):
        profiles, urls, artifacts = [], [], []

        def capture(browser, url, profile, collector, artifact_id):
            self.assertEqual(self.browser, browser)
            self.assertTrue(profile.is_dir())
            profiles.append(profile)
            urls.append(url)
            artifacts.append(artifact_id)
            _capture(collector, artifact_id, self.png)

        with self._boundaries(capture) as mocks, _fake_runtime_profile_v2():
            result = self._run()
        mocks["reader"].load.assert_called_once_with(
            self.fixture.bundle.project_id,
            self.fixture.bundle.skeleton_json_sha256,
            self.fixture.bundle.bundle_sha256,
        )
        mocks["bridge"].build.assert_not_called()
        call = mocks["bridge"].build_from_verified.call_args
        self.assertIs(self.fixture.bundle, call.args[0])
        self.assertEqual(1, mocks["bridge"].build_from_verified.call_count)
        self.assertEqual(2, mocks["runtime"].call_count)
        self.assertEqual(len(artifacts) + 1, mocks["recheck"].call_count)
        self.assertEqual(result.artifact_count, len(artifacts))
        with _fake_runtime_profile_v2():
            exact = subject._require_issued_spine42_v3_runtime_run_v2(result)
        with self.assertRaises(ValueError):
            subject._require_issued_spine42_v3_runtime_run_v2(result)
        self.assertEqual(exact[4].artifact_ids, tuple(artifacts))
        self.assertEqual(tuple(result.capture_bytes), tuple(artifacts))
        self.assertEqual(tuple(
            row["artifact"]["artifact_id"] for row in result.reports
        ), tuple(artifacts))
        self.assertTrue(all(url.startswith("http://127.0.0.1:") for url in urls))
        self.assertTrue(all(not profile.exists() for profile in profiles))
        self.assertTrue(mocks["lease"].closed)
        server_lease = mocks["server_leases"][0]
        self.assertEqual(len(artifacts) + 1, server_lease.health_checks)
        self.assertTrue(server_lease.closed)
        self.assertNotIn(str(self.root), repr(result))
        self.assertTrue(result.license_acknowledged)
        self.assertFalse(hasattr(result, "exact_inputs"))
        self.assertIsInstance(exact[0], VerifiedSpine42V3BundleV2)
        self.assertIsInstance(exact[1], VerifiedSpine42V3RuntimeSourceV2)
        self.assertIsInstance(exact[4], Spine42V3RuntimeSessionsV2)
        self.assertIsInstance(exact[5],
                              Spine42V3RuntimeCaptureSnapshotV2)
        detached = asdict(result)
        _assert_path_free(self, detached, str(self.root))
        _assert_path_free(self, result.document, str(self.root))
        self.assertTrue(all(value is False
                            for value in result.document["authority"].values()))
        self.assertTrue(all(value is False
                            for value in result.document["release"].values()))
        for forged in (type(result)(**detached), replace(result)):
            with self.assertRaisesRegex(
                Spine42V3RuntimeRunnerV2Error, "not runner-issued",
            ):
                subject._require_issued_spine42_v3_runtime_run_v2(forged)
        for forbidden in (
            "compute_spine42_v3_raster_metrics",
            "Spine42V3RuntimeStore", "build_spine42_v3_runtime_evidence",
        ):
            self.assertNotIn(forbidden, vars(subject))
        object.__setattr__(result, "artifact_count", result.artifact_count + 1)
        with _fake_runtime_profile_v2(), self.assertRaisesRegex(
                Spine42V3RuntimeRunnerV2Error, "differs from exact inputs",
            ):
                subject._require_issued_spine42_v3_runtime_run_v2(result)

    def test_license_and_windows_gates_precede_every_io_boundary(self):
        names = (
            "_require_windows", "VerifiedSpine42V3BundleReaderV2",
            "VerifiedSpine42V3RuntimeSourceBridgeV2",
            "require_runtime_package", "LockedBrowserExecutableLease",
            "create_spine42_v3_runtime_capture_server_v2",
            "run_spine42_v3_headless_capture_v2",
        )
        patches = [patch.object(subject, name) for name in names]
        mocks = [item.start() for item in patches]
        try:
            for value in (False, None, 1, "true"):
                with self.subTest(value=value), self.assertRaisesRegex(
                    Spine42V3RuntimeRunnerV2Error,
                    "license acknowledgement",
                ):
                    self._run(license_acknowledged=value)
            for mock in mocks:
                mock.assert_not_called()
        finally:
            for item in reversed(patches):
                item.stop()

        io_names = names[1:]
        patches = [patch.object(subject, name) for name in io_names]
        mocks = [item.start() for item in patches]
        try:
            with patch.object(subject.os, "name", "posix"), \
                    self.assertRaisesRegex(
                        Spine42V3RuntimeRunnerV2Error, "only on Windows",
                    ):
                self._run()
            for mock in mocks:
                mock.assert_not_called()
        finally:
            for item in reversed(patches):
                item.stop()

    def test_missing_error_or_future_post_fails_exact_prefix(self):
        def runtime_error(_browser, _url, _profile, collector, artifact_id):
            collector.record_error(artifact_id, "WebGL failed")

        def future(_browser, _url, _profile, collector, artifact_id):
            _capture(collector, artifact_id, self.png)
            _capture(collector, collector.artifact_ids[1], self.png)

        for capture in (lambda *_args: None, runtime_error, future):
            with self.subTest(capture=capture), self._boundaries(capture), \
                    _fake_runtime_profile_v2(), self.assertRaisesRegex(
                        Spine42V3RuntimeRunnerV2Error,
                        "exact completed prefix",
                    ):
                self._run()

    def test_browser_and_runtime_drift_fail_closed(self):
        capture = lambda _b, _u, _p, collector, artifact: _capture(
            collector, artifact, self.png,
        )
        with self._boundaries(capture) as mocks, _fake_runtime_profile_v2():
            mocks["recheck"].side_effect = [
                self.browser, BrowserExecutableSnapshotError("changed"),
            ]
            with self.assertRaises(Spine42V3RuntimeRunnerV2Error):
                self._run()
        self.assertEqual(1, mocks["driver"].call_count)
        self.assertTrue(mocks["lease"].closed)
        changed = replace(self.runtime, license_sha256="d" * 64)
        with self._boundaries(capture) as mocks, _fake_runtime_profile_v2():
            mocks["runtime"].side_effect = [self.runtime, changed]
            with self.assertRaisesRegex(
                Spine42V3RuntimeRunnerV2Error, "runtime package changed",
            ):
                self._run()

    def test_unhealthy_server_mid_capture_fails_and_closes_leases(self):
        capture = lambda _b, _u, _p, collector, artifact: _capture(
            collector, artifact, self.png,
        )
        with self._boundaries(capture, server_fail_at=2) as mocks, \
                _fake_runtime_profile_v2(), self.assertRaises(
                    Spine42V3RuntimeRunnerV2Error,
                ):
            self._run()
        self.assertEqual(1, mocks["driver"].call_count)
        self.assertTrue(mocks["lease"].closed)
        self.assertTrue(mocks["server_leases"][0].closed)

    def test_non_v2_reader_value_fails_before_runtime_or_browser(self):
        reader, runtime, lease = Mock(), Mock(), Mock()
        reader.load.return_value = object()
        with patch.object(subject, "_require_windows"), patch.object(
            subject, "VerifiedSpine42V3BundleReaderV2", return_value=reader,
        ), patch.object(
            subject, "require_runtime_package", runtime,
        ), patch.object(
            subject, "LockedBrowserExecutableLease", lease,
        ), self.assertRaises(Spine42V3RuntimeRunnerV2Error):
            self._run()
        self.assertEqual(1, reader.load.call_count)
        runtime.assert_not_called()
        lease.assert_not_called()

    def _run(self, *, license_acknowledged=True):
        bundle = self.fixture.bundle
        return run_spine42_v3_runtime_capture_v2(
            self.fixture.source_fixture.state_root, bundle.project_id,
            skeleton_json_sha256=bundle.skeleton_json_sha256,
            spine42_v3_bundle_sha256=bundle.bundle_sha256,
            runtime_root=self.root / "runtime",
            browser_executable=self.root / "chrome.exe",
            license_acknowledged=license_acknowledged,
        )

    def _boundaries(self, capture, *, server_fail_at=None):
        test = self

        class Boundaries:
            def __enter__(inner):
                inner.reader, inner.bridge = Mock(), Mock()
                inner.reader.load.return_value = test.fixture.bundle
                inner.bridge.build_from_verified.return_value = (
                    test.fixture.source
                )
                inner.lease = _BrowserLease(test.browser)
                inner.server_leases = []

                def guarded(*args):
                    if not inner.lease.active:
                        raise AssertionError("browser lease is not active")
                    return capture(*args)

                def server_lease(server):
                    lease = _ServerLease(server, fail_at=server_fail_at)
                    inner.server_leases.append(lease)
                    return lease

                inner.patches = (
                    patch.object(subject, "_require_windows"),
                    patch.object(
                        subject, "VerifiedSpine42V3BundleReaderV2",
                        return_value=inner.reader,
                    ),
                    patch.object(
                        subject, "VerifiedSpine42V3RuntimeSourceBridgeV2",
                        return_value=inner.bridge,
                    ),
                    patch.object(
                        subject, "require_runtime_package",
                        side_effect=[test.runtime, test.runtime],
                    ),
                    patch.object(
                        subject, "LockedBrowserExecutableLease",
                        return_value=inner.lease,
                    ),
                    patch.object(
                        subject, "recheck_browser_executable",
                        return_value=test.browser,
                    ),
                    patch.object(
                        subject, "run_spine42_v3_headless_capture_v2",
                        side_effect=guarded,
                    ),
                    patch.object(
                        subject, "BodySwayCaptureServerLease",
                        side_effect=server_lease,
                    ),
                )
                mocks = [item.start() for item in inner.patches]
                inner.mocks = dict(zip((
                    "windows", "reader_factory", "bridge_factory",
                    "runtime", "lease_factory", "recheck", "driver",
                    "server_lease_factory",
                ), mocks, strict=True))
                inner.mocks.update({
                    "reader": inner.reader, "bridge": inner.bridge,
                    "lease": inner.lease,
                    "server_leases": inner.server_leases,
                })
                return inner.mocks

            def __exit__(inner, kind, value, traceback):
                for item in reversed(inner.patches):
                    item.stop()

        return Boundaries()


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


if __name__ == "__main__":
    unittest.main()
