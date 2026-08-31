"""Tests for allowlisted, path-free P10 runtime environment discovery."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.browser_executable_snapshot import (  # noqa: E402
    BrowserExecutableSnapshot,
    BrowserExecutableSnapshotError,
)
from autospine_workbench.p10_runtime_environment import (  # noqa: E402
    FORMAT,
    FORMAT_VERSION,
    P10RuntimeEnvironmentError,
    RUNTIME_RELATIVE_PATH,
    discover_p10_runtime_environment,
)
from autospine_workbench.spine42_contract import (  # noqa: E402
    SPINE_RUNTIME_PACKAGE,
    SPINE_RUNTIME_VERSION,
)
from autospine_workbench.spine42_runtime_inputs import (  # noqa: E402
    Spine42RuntimeInputError,
    Spine42RuntimePackage,
)


SHA = {
    "js": "1" * 64, "css": "2" * 64, "package": "3" * 64,
    "license": "4" * 64, "browser": "5" * 64,
}


class P10RuntimeEnvironmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.runtime_path = self.root / RUNTIME_RELATIVE_PATH
        self.runtime_path.mkdir(parents=True)
        self.chrome = self.root / "allowed" / "chrome.exe"
        self.chrome.parent.mkdir()
        self.chrome.write_bytes(b"chrome")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_exact_candidates_are_exposed_without_paths_or_authorization(self):
        runtime = self._runtime()
        browser = self._browser(self.chrome)
        with self._discovery(runtime, browser) as calls:
            result = discover_p10_runtime_environment(self.root)
        self.assertEqual(self.runtime_path, calls[0].call_args.args[0])
        self.assertEqual(self.chrome, calls[1].call_args.args[0])
        self.assertIs(result.runtime, runtime)
        self.assertIs(result.browser, browser)
        self.assertTrue(result.available)
        expected = {
            "format": FORMAT, "format_version": FORMAT_VERSION,
            "available": True,
            "runtime": {
                "available": True, "package": SPINE_RUNTIME_PACKAGE,
                "version": SPINE_RUNTIME_VERSION,
                "javascript_sha256": SHA["js"],
                "stylesheet_sha256": SHA["css"],
                "package_json_sha256": SHA["package"],
                "license_sha256": SHA["license"],
                "license_acknowledged": False,
                "license_file_presence_is_authorization": False,
            },
            "browser": {
                "available": True, "family": "google-chrome",
                "reported_version": "152.0.7977.64",
                "executable_sha256": SHA["browser"],
                "size_bytes": 4096,
            },
        }
        self.assertEqual(expected, result.public_document())
        exposed = repr(result.public_document())
        self.assertNotIn(str(self.root), exposed)
        self.assertNotIn("chrome.exe", exposed)

    def test_missing_candidates_are_path_free_and_unavailable(self):
        empty = self.root / "empty"
        empty.mkdir()
        with patch(
            "autospine_workbench.p10_runtime_environment._windows_host",
            return_value=True,
        ), patch(
            "autospine_workbench.p10_runtime_environment."
            "WINDOWS_STANDARD_CHROME_PATHS",
            (empty / "chrome.exe",),
        ):
            document = discover_p10_runtime_environment(empty).public_document()
        self.assertFalse(document["available"])
        self.assertFalse(document["runtime"]["available"])
        self.assertFalse(document["browser"]["available"])
        self.assertEqual(SPINE_RUNTIME_PACKAGE, document["runtime"]["package"])
        self.assertEqual(SPINE_RUNTIME_VERSION, document["runtime"]["version"])
        self.assertIsNone(document["runtime"]["license_sha256"])
        self.assertFalse(document["runtime"]["license_acknowledged"])

    def test_invalid_exact_candidates_are_not_downgraded_or_exposed(self):
        with patch(
            "autospine_workbench.p10_runtime_environment.require_runtime_package",
            side_effect=Spine42RuntimeInputError("private runtime path"),
        ), patch(
            "autospine_workbench.p10_runtime_environment._windows_host",
            return_value=True,
        ), patch(
            "autospine_workbench.p10_runtime_environment."
            "WINDOWS_STANDARD_CHROME_PATHS",
            (self.chrome,),
        ), patch(
            "autospine_workbench.p10_runtime_environment."
            "snapshot_browser_executable",
            side_effect=BrowserExecutableSnapshotError("private browser path"),
        ):
            document = discover_p10_runtime_environment(self.root).public_document()
        self.assertFalse(document["available"])
        self.assertFalse(document["runtime"]["available"])
        self.assertFalse(document["browser"]["available"])
        self.assertNotIn("path", repr(document).lower())

    def test_only_allowlisted_paths_are_considered_in_priority_order(self):
        first = self.root / "first" / "chrome.exe"
        second = self.root / "second" / "chrome.exe"
        other = self.root / "other" / "chrome.exe"
        for path in (first, second, other):
            path.parent.mkdir()
            path.write_bytes(b"x")
        browser = self._browser(first)
        with patch(
            "autospine_workbench.p10_runtime_environment.require_runtime_package",
            return_value=self._runtime(),
        ), patch(
            "autospine_workbench.p10_runtime_environment._windows_host",
            return_value=True,
        ), patch(
            "autospine_workbench.p10_runtime_environment."
            "WINDOWS_STANDARD_CHROME_PATHS",
            (first, second),
        ), patch(
            "autospine_workbench.p10_runtime_environment."
            "snapshot_browser_executable",
            return_value=browser,
        ) as snapshot:
            result = discover_p10_runtime_environment(self.root)
        snapshot.assert_called_once_with(first)
        self.assertIs(result.browser, browser)
        self.assertNotEqual(other, Path(result.browser.path))

    def test_non_windows_never_probes_browser_candidates(self):
        with patch(
            "autospine_workbench.p10_runtime_environment.require_runtime_package",
            return_value=self._runtime(),
        ), patch(
            "autospine_workbench.p10_runtime_environment._windows_host",
            return_value=False,
        ), patch(
            "autospine_workbench.p10_runtime_environment."
            "snapshot_browser_executable",
        ) as snapshot:
            result = discover_p10_runtime_environment(self.root)
        snapshot.assert_not_called()
        self.assertFalse(result.available)
        self.assertIsNone(result.browser)

    def test_public_projection_is_a_fresh_detached_copy(self):
        with self._discovery(self._runtime(), self._browser(self.chrome)):
            result = discover_p10_runtime_environment(self.root)
        first = result.public_document()
        first["runtime"]["package"] = "changed"
        self.assertEqual(
            SPINE_RUNTIME_PACKAGE,
            result.public_document()["runtime"]["package"],
        )

    def test_invalid_state_root_fails_before_discovery(self):
        with self.assertRaises(P10RuntimeEnvironmentError):
            discover_p10_runtime_environment(None)  # type: ignore[arg-type]

    def _runtime(self) -> Spine42RuntimePackage:
        return Spine42RuntimePackage(
            self.runtime_path,
            self.runtime_path / "spine-player.min.js",
            self.runtime_path / "spine-player.min.css",
            self.runtime_path / "LICENSE",
            b"js", b"css", SHA["js"], SHA["css"],
            SHA["package"], SHA["license"],
        )

    @staticmethod
    def _browser(path: Path) -> BrowserExecutableSnapshot:
        return BrowserExecutableSnapshot(
            str(path), "google-chrome", "152.0.7977.64",
            "6" * 64, SHA["browser"], 4096,
        )

    def _discovery(self, runtime, browser):
        runtime_patch = patch(
            "autospine_workbench.p10_runtime_environment.require_runtime_package",
            return_value=runtime,
        )
        windows_patch = patch(
            "autospine_workbench.p10_runtime_environment._windows_host",
            return_value=True,
        )
        paths_patch = patch(
            "autospine_workbench.p10_runtime_environment."
            "WINDOWS_STANDARD_CHROME_PATHS",
            (self.chrome,),
        )
        browser_patch = patch(
            "autospine_workbench.p10_runtime_environment."
            "snapshot_browser_executable",
            return_value=browser,
        )

        class _Patches:
            def __enter__(inner):
                inner.runtime = runtime_patch.start()
                windows_patch.start()
                paths_patch.start()
                inner.browser = browser_patch.start()
                return inner.runtime, inner.browser

            def __exit__(inner, *_args):
                browser_patch.stop()
                paths_patch.stop()
                windows_patch.stop()
                runtime_patch.stop()

        return _Patches()


if __name__ == "__main__":
    unittest.main()
