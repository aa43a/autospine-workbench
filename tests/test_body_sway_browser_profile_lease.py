"""Tests for fail-closed temporary browser-profile cleanup."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.body_sway_browser_profile_lease import (  # noqa: E402
    BodySwayBrowserProfileLease,
    BodySwayBrowserProfileLeaseError,
)


class _CleanupOnceTemporary:
    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.name = self.temporary.name
        self.calls = 0

    def cleanup(self) -> None:
        self.calls += 1
        if self.calls == 1:
            raise OSError("profile cleanup failed")
        self.temporary.cleanup()


class _NoCleanupTemporary(_CleanupOnceTemporary):
    def cleanup(self) -> None:
        self.calls += 1


class BodySwayBrowserProfileLeaseTests(unittest.TestCase):
    def test_success_removes_profile_before_return(self):
        with BodySwayBrowserProfileLease() as profile:
            self.assertTrue(profile.is_dir())
        self.assertFalse(profile.exists())

    def test_transient_cleanup_failure_is_retried_and_recovers(self):
        temporary = _CleanupOnceTemporary()
        primary = LookupError("capture failed")
        try:
            with patch(
                "autospine_workbench.body_sway_browser_profile_lease."
                "tempfile.TemporaryDirectory",
                return_value=temporary,
            ):
                with self.assertRaises(LookupError) as raised:
                    with BodySwayBrowserProfileLease():
                        raise primary
            self.assertIs(primary, raised.exception)
            self.assertEqual(2, temporary.calls)
            self.assertFalse(Path(temporary.name).exists())
            self.assertFalse(getattr(primary, "__notes__", ()))
        finally:
            temporary.temporary.cleanup()

    def test_transient_cleanup_failure_without_capture_error_recovers(self):
        temporary = _CleanupOnceTemporary()
        try:
            with patch(
                "autospine_workbench.body_sway_browser_profile_lease."
                "tempfile.TemporaryDirectory",
                return_value=temporary,
            ):
                with BodySwayBrowserProfileLease():
                    pass
            self.assertEqual(2, temporary.calls)
            self.assertFalse(Path(temporary.name).exists())
        finally:
            temporary.temporary.cleanup()

    def test_silent_cleanup_noop_is_detected(self):
        temporary = _NoCleanupTemporary()
        try:
            with patch(
                "autospine_workbench.body_sway_browser_profile_lease."
                "tempfile.TemporaryDirectory",
                return_value=temporary,
            ), self.assertRaisesRegex(
                BodySwayBrowserProfileLeaseError, "was not removed"
            ):
                with BodySwayBrowserProfileLease():
                    pass
        finally:
            temporary.temporary.cleanup()

    def test_permanent_cleanup_failure_preserves_primary_with_notes(self):
        temporary = _NoCleanupTemporary()
        primary = LookupError("capture failed")
        try:
            with patch(
                "autospine_workbench.body_sway_browser_profile_lease."
                "tempfile.TemporaryDirectory",
                return_value=temporary,
            ), self.assertRaises(LookupError) as raised:
                with BodySwayBrowserProfileLease():
                    raise primary
            self.assertIs(primary, raised.exception)
            self.assertEqual(2, temporary.calls)
            self.assertTrue(any(
                "bounded cleanup retries" in note
                for note in getattr(primary, "__notes__", ())
            ))
        finally:
            temporary.temporary.cleanup()


if __name__ == "__main__":
    unittest.main()
