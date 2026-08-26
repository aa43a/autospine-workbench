from __future__ import annotations

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import autospine_workbench.browser_executable_snapshot as subject
from autospine_workbench.browser_executable_snapshot import (
    BrowserExecutableSnapshot,
    BrowserExecutableSnapshotError,
    recheck_browser_executable,
    snapshot_browser_executable,
)
from autospine_workbench.browser_version_identity import BrowserVersionIdentity


CHROME_IDENTITY = b"Google Chrome 142.0.7444.60\n"


class BrowserExecutableSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve(strict=True)
        self.executable = self.root / "chrome-test.exe"
        self.executable.write_bytes(b"fixed fake executable bytes")
        self.executable.chmod(
            self.executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @contextmanager
    def version(self, family: str = "google-chrome", version: str = "142.0.7444.60"):
        label = "Google Chrome" if family == "google-chrome" else "Chromium"
        identity = BrowserVersionIdentity(
            family, version, f"{label} {version}\n".encode()
        )
        with patch.object(subject, "identify_browser_version", return_value=identity):
            yield

    def test_snapshots_google_chrome_with_exact_byte_identity(self) -> None:
        raw = self.executable.read_bytes()
        with self.version():
            snapshot = snapshot_browser_executable(self.executable)

        self.assertEqual("google-chrome", snapshot.family)
        self.assertEqual("142.0.7444.60", snapshot.reported_version)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), snapshot.executable_sha256)
        self.assertEqual(
            hashlib.sha256(CHROME_IDENTITY).hexdigest(),
            snapshot.version_output_sha256,
        )
        self.assertEqual(len(raw), snapshot.size_bytes)
        self.assertEqual(str(self.executable), snapshot.path)
        self.assertEqual(
            {
                "format": "autospine-browser-executable-snapshot",
                "version": 1,
                "path": str(self.executable),
                "family": "google-chrome",
                "reported_version": "142.0.7444.60",
                "version_output_sha256": hashlib.sha256(CHROME_IDENTITY).hexdigest(),
                "executable_sha256": hashlib.sha256(raw).hexdigest(),
                "size_bytes": len(raw),
            },
            snapshot.to_document(),
        )

    def test_snapshots_chromium_family(self) -> None:
        with self.version("chromium", "141.0.7390.0"):
            snapshot = snapshot_browser_executable(self.executable)
        self.assertEqual("chromium", snapshot.family)
        self.assertEqual("141.0.7390.0", snapshot.reported_version)

    def test_requires_absolute_canonical_regular_executable(self) -> None:
        with self.assertRaisesRegex(BrowserExecutableSnapshotError, "absolute"):
            snapshot_browser_executable(Path("chrome.exe"))
        lexical_alias = self.root / "folder" / ".." / self.executable.name
        with self.assertRaisesRegex(BrowserExecutableSnapshotError, "lexical aliases"):
            snapshot_browser_executable(lexical_alias)
        with self.assertRaisesRegex(BrowserExecutableSnapshotError, "regular file"):
            snapshot_browser_executable(self.root)

    def test_rejects_file_and_parent_symlinks_when_supported(self) -> None:
        alias = self.root / "chrome-alias.exe"
        parent_alias = self.root / "parent-alias"
        real_parent = self.root / "real-parent"
        real_parent.mkdir()
        nested = real_parent / "chrome.exe"
        nested.write_bytes(b"browser")
        nested.chmod(nested.stat().st_mode | stat.S_IXUSR)
        try:
            alias.symlink_to(self.executable)
            parent_alias.symlink_to(real_parent, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlinks unavailable: {exc}")
        try:
            with self.assertRaises(BrowserExecutableSnapshotError):
                snapshot_browser_executable(alias)
            with self.assertRaises(BrowserExecutableSnapshotError):
                snapshot_browser_executable(parent_alias / nested.name)
        finally:
            alias.unlink(missing_ok=True)
            parent_alias.unlink(missing_ok=True)

    def test_recognizes_windows_reparse_attribute_as_alias(self) -> None:
        metadata = type("Metadata", (), {
            "st_mode": stat.S_IFREG,
            "st_file_attributes": 0x400,
        })()
        with patch.object(Path, "is_junction", return_value=False, create=True):
            self.assertTrue(subject._is_alias(self.executable, metadata))

    def test_enforces_executable_size_limit(self) -> None:
        with patch.object(subject, "MAX_EXECUTABLE_BYTES", 4), self.version():
            with self.assertRaisesRegex(BrowserExecutableSnapshotError, "size"):
                snapshot_browser_executable(self.executable)

    def test_detects_change_across_pre_and_post_version_hashes(self) -> None:
        with patch.object(
            subject,
            "_hash_executable",
            side_effect=[("a" * 64, 25), ("b" * 64, 25)],
        ), self.version():
            with self.assertRaisesRegex(BrowserExecutableSnapshotError, "version"):
                snapshot_browser_executable(self.executable)

    def test_hash_accepts_windows_path_handle_ctime_difference(self) -> None:
        path_state = SimpleNamespace(
            st_mode=stat.S_IFREG,
            st_dev=7,
            st_ino=11,
            st_size=3,
            st_mtime_ns=13,
            st_ctime_ns=17,
        )
        handle_state = SimpleNamespace(
            **{**vars(path_state), "st_ctime_ns": 19}
        )
        changed_handle = SimpleNamespace(
            **{**vars(handle_state), "st_ctime_ns": 23}
        )
        self.assertTrue(subject._same_content_state(path_state, handle_state))
        self.assertFalse(subject._same_path_snapshot(path_state, handle_state))
        self.assertFalse(subject._same_handle_snapshot(handle_state, changed_handle))
        with patch.object(
            Path, "lstat", side_effect=[path_state, path_state]
        ), patch.object(subject.os, "open", return_value=23), patch.object(
            subject.os, "fstat", side_effect=[handle_state, handle_state]
        ), patch.object(
            subject.os, "read", side_effect=[b"abc", b""]
        ), patch.object(subject.os, "close"):
            digest, size = subject._hash_executable(self.executable)
        self.assertEqual(hashlib.sha256(b"abc").hexdigest(), digest)
        self.assertEqual(3, size)

    def test_descriptor_close_failure_rejects_an_otherwise_valid_hash(self) -> None:
        state = self.executable.lstat()
        with patch.object(
            Path, "lstat", side_effect=[state, state]
        ), patch.object(subject.os, "open", return_value=23), patch.object(
            subject.os, "fstat", side_effect=[state, state]
        ), patch.object(
            subject.os, "read", side_effect=[self.executable.read_bytes(), b""]
        ), patch.object(
            subject.os, "close", side_effect=OSError("close failed")
        ), self.assertRaisesRegex(
            BrowserExecutableSnapshotError, "descriptor"
        ):
            subject._hash_executable(self.executable)

    def test_descriptor_close_failure_is_noted_on_primary_hash_error(self) -> None:
        state = self.executable.lstat()
        with patch.object(
            Path, "lstat", return_value=state
        ), patch.object(subject.os, "open", return_value=23), patch.object(
            subject.os, "fstat", return_value=state
        ), patch.object(
            subject.os, "read", side_effect=OSError("read failed")
        ), patch.object(
            subject.os, "close", side_effect=OSError("close failed")
        ), self.assertRaisesRegex(
            BrowserExecutableSnapshotError, "hashed safely"
        ) as raised:
            subject._hash_executable(self.executable)
        self.assertTrue(any(
            "descriptor cleanup also failed" in note.lower()
            for note in getattr(raised.exception, "__notes__", ())
        ))

    @unittest.skipUnless(os.name == "nt", "Windows VERSIONINFO smoke test")
    def test_real_installed_chrome_snapshot_uses_version_info(self) -> None:
        chrome = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
        if not chrome.is_file():
            self.skipTest("system Chrome is not installed at the standard path")
        snapshot = snapshot_browser_executable(chrome)
        self.assertEqual("google-chrome", snapshot.family)
        self.assertRegex(snapshot.reported_version, r"^\d+(?:\.\d+){3}$")
        identity = f"Google Chrome {snapshot.reported_version}\n".encode()
        self.assertEqual(
            hashlib.sha256(identity).hexdigest(), snapshot.version_output_sha256
        )
        self.assertEqual(chrome.stat().st_size, snapshot.size_bytes)

    def test_recheck_requires_every_field_and_current_bytes(self) -> None:
        with self.version():
            expected = snapshot_browser_executable(self.executable)
            self.assertEqual(expected, recheck_browser_executable(expected))
            self.executable.write_bytes(b"changed executable contents")
            with self.assertRaisesRegex(BrowserExecutableSnapshotError, "changed"):
                recheck_browser_executable(expected)
        with self.assertRaises(BrowserExecutableSnapshotError):
            recheck_browser_executable(expected.to_document())  # type: ignore[arg-type]

    def test_recheck_rejects_changed_reported_version(self) -> None:
        with self.version():
            expected = snapshot_browser_executable(self.executable)
        with self.version(version="143.0.7444.60"):
            with self.assertRaisesRegex(BrowserExecutableSnapshotError, "changed"):
                recheck_browser_executable(expected)


if __name__ == "__main__":
    unittest.main()
