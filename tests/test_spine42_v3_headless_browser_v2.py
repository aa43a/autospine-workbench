"""Exact v2 adapter tests for the frozen browser process driver."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.browser_executable_snapshot import (  # noqa: E402
    BrowserExecutableSnapshot,
)
from autospine_workbench.spine42_v3_headless_browser import (  # noqa: E402
    Spine42V3HeadlessBrowserError,
)
from autospine_workbench.spine42_v3_headless_browser_v2 import (  # noqa: E402
    Spine42V3HeadlessBrowserV2Error,
    run_spine42_v3_headless_capture_v2,
)
from autospine_workbench.spine42_v3_runtime_capture_collector import (  # noqa: E402
    Spine42V3RuntimeCaptureCollector,
)
from autospine_workbench.spine42_v3_runtime_capture_collector_v2 import (  # noqa: E402
    Spine42V3RuntimeCaptureCollectorV2,
)
from tests.test_spine42_v3_runtime_capture_harness import (  # noqa: E402
    HarnessFixture,
)
from tests.test_spine42_v3_runtime_capture_harness_v2 import (  # noqa: E402
    V2HarnessFixture,
)


DRIVER = (
    "autospine_workbench.spine42_v3_headless_browser_v2."
    "run_spine42_v3_headless_capture"
)
POPEN = "autospine_workbench.spine42_v3_headless_browser.subprocess.Popen"


class Spine42V3HeadlessBrowserV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        root = Path(cls.temporary.name)
        cls.v2 = V2HarnessFixture(root / "v2")
        cls.v1 = HarnessFixture(root / "v1")
        cls.browser = BrowserExecutableSnapshot(
            path=str((root / "browser.exe").absolute()),
            family="chrome", reported_version="1",
            version_output_sha256="a" * 64,
            executable_sha256="b" * 64, size_bytes=1,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.collector = Spine42V3RuntimeCaptureCollectorV2(self.v2.sessions)
        self.artifact_id = self.collector.artifact_ids[0]
        self.profile = Path(self.temporary.name) / self.id().split(".")[-1]
        self.profile.mkdir()
        self.url = f"http://127.0.0.1:8765/capture/{self.artifact_id}"

    def test_exact_v2_inputs_delegate_once(self):
        with patch(DRIVER) as driver:
            result = run_spine42_v3_headless_capture_v2(
                self.browser, self.url, self.profile,
                self.collector, self.artifact_id,
            )
        self.assertIsNone(result)
        driver.assert_called_once_with(
            self.browser, self.url, self.profile,
            self.collector, self.artifact_id,
        )

    def test_wrong_browser_and_collectors_never_reach_driver(self):
        v1_collector = Spine42V3RuntimeCaptureCollector(self.v1.sessions)
        for browser, collector in (
            (object(), self.collector),
            (self.browser, v1_collector),
            (self.browser, object()),
        ):
            with self.subTest(browser=type(browser), collector=type(collector)), \
                    patch(DRIVER) as driver, self.assertRaises(
                        Spine42V3HeadlessBrowserV2Error
                    ):
                run_spine42_v3_headless_capture_v2(
                    browser, self.url, self.profile,
                    collector, self.artifact_id,
                )
            driver.assert_not_called()

    def test_url_and_profile_fail_before_process_launch(self):
        occupied = self.profile / "not-fresh"
        occupied.write_text("x", encoding="utf-8")
        url_profile = self.profile.parent / f"{self.profile.name}-url"
        url_profile.mkdir()
        for url, profile in (
            ("https://example.invalid/capture/x", url_profile),
            (self.url, self.profile),
        ):
            with self.subTest(url=url, profile=profile), patch(POPEN) as launch, \
                    self.assertRaises(Spine42V3HeadlessBrowserV2Error):
                run_spine42_v3_headless_capture_v2(
                    self.browser, url, profile,
                    self.collector, self.artifact_id,
                )
            launch.assert_not_called()

    def test_driver_error_is_mapped_with_cause_and_cleanup_notes(self):
        failure = Spine42V3HeadlessBrowserError("driver failed")
        failure.add_note("Cleanup also failed: synthetic")
        with patch(DRIVER, side_effect=failure), self.assertRaisesRegex(
            Spine42V3HeadlessBrowserV2Error, "driver failed"
        ) as raised:
            run_spine42_v3_headless_capture_v2(
                self.browser, self.url, self.profile,
                self.collector, self.artifact_id,
            )
        self.assertIs(failure, raised.exception.__cause__)
        self.assertEqual(
            ["Cleanup also failed: synthetic"], raised.exception.__notes__
        )


if __name__ == "__main__":
    unittest.main()
