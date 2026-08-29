"""Regression tests for cross-platform atomic staging directories."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.atomic_staging import (  # noqa: E402
    create_same_parent_staging,
)


class AtomicStagingTests(unittest.TestCase):
    def test_windows_name_collision_retries_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory) / "parent"
            parent.mkdir()
            prefix = ".0123456789ab."
            (parent / f"{prefix}occupied").mkdir()
            with patch(
                "autospine_workbench.atomic_staging._WINDOWS", True,
            ), patch(
                "autospine_workbench.atomic_staging.secrets.token_hex",
                side_effect=("occupied", "available"),
            ):
                staging = create_same_parent_staging(parent, prefix=prefix)
            self.assertEqual(parent / f"{prefix}available", staging)
            self.assertTrue(staging.is_dir())

    @unittest.skipUnless(os.name == "nt", "Windows DACL regression")
    def test_windows_rename_preserves_parent_acl_inheritance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory) / "publication-parent"
            parent.mkdir()
            staging = create_same_parent_staging(
                parent, prefix=".0123456789ab.",
            )
            destination = parent / ("a" * 64)
            os.rename(staging, destination)
            self.assertFalse(_windows_dacl_is_protected(parent))
            self.assertFalse(_windows_dacl_is_protected(destination))


def _windows_dacl_is_protected(path: Path) -> bool:
    dacl_security_information = 0x00000004
    se_dacl_protected = 0x1000
    error_insufficient_buffer = 122
    library = ctypes.WinDLL("advapi32", use_last_error=True)
    get_file_security = library.GetFileSecurityW
    get_file_security.argtypes = (
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
    )
    get_file_security.restype = wintypes.BOOL
    get_control = library.GetSecurityDescriptorControl
    get_control.argtypes = (
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_ushort),
        ctypes.POINTER(wintypes.DWORD),
    )
    get_control.restype = wintypes.BOOL
    required = wintypes.DWORD()
    get_file_security(
        str(path), dacl_security_information, None, 0,
        ctypes.byref(required),
    )
    if ctypes.get_last_error() != error_insufficient_buffer:
        raise ctypes.WinError(ctypes.get_last_error())
    descriptor = ctypes.create_string_buffer(required.value)
    if not get_file_security(
        str(path), dacl_security_information, descriptor,
        required.value, ctypes.byref(required),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    control = ctypes.c_ushort()
    revision = wintypes.DWORD()
    if not get_control(
        descriptor, ctypes.byref(control), ctypes.byref(revision),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return bool(control.value & se_dacl_protected)


if __name__ == "__main__":
    unittest.main()
