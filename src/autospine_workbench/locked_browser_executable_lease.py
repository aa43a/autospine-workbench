"""Windows file lease that stabilizes a browser launcher during capture."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import operator
import os
from pathlib import Path

from .browser_executable_snapshot import (
    BrowserExecutableSnapshot,
    recheck_browser_executable,
    snapshot_browser_executable,
)


GENERIC_READ = 0x80000000
FILE_SHARE_READ = 0x00000001
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x00000080
MAX_FINAL_PATH_CHARS = 32_768
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_IS_WINDOWS = os.name == "nt"


class LockedBrowserExecutableLeaseError(RuntimeError):
    """Raised unless the browser file stays locked for the transaction."""


class _WindowsBrowserFileBackend:
    def __init__(self) -> None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._create_file = kernel32.CreateFileW
        self._create_file.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        self._create_file.restype = wintypes.HANDLE
        self._final_path = kernel32.GetFinalPathNameByHandleW
        self._final_path.argtypes = [
            wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD,
        ]
        self._final_path.restype = wintypes.DWORD
        self._close = kernel32.CloseHandle
        self._close.argtypes = [wintypes.HANDLE]
        self._close.restype = wintypes.BOOL

    def open_read_locked(self, path: Path) -> int:
        handle = self._create_file(
            os.fspath(path),
            GENERIC_READ,
            FILE_SHARE_READ,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,
            None,
        )
        value = operator.index(handle) if handle else 0
        if not value or value == INVALID_HANDLE_VALUE:
            self._raise_api_error("CreateFileW")
        return value

    def final_path(self, handle: int) -> Path:
        buffer = ctypes.create_unicode_buffer(MAX_FINAL_PATH_CHARS)
        length = int(self._final_path(
            handle, buffer, MAX_FINAL_PATH_CHARS, 0
        ))
        if length == 0:
            self._raise_api_error("GetFinalPathNameByHandleW")
        if length >= MAX_FINAL_PATH_CHARS:
            raise LockedBrowserExecutableLeaseError(
                "Browser executable final path exceeds the allowed length"
            )
        return Path(_strip_windows_device_prefix(buffer.value))

    def close(self, handle: int) -> None:
        if not self._close(handle):
            self._raise_api_error("CloseHandle")

    @staticmethod
    def _raise_api_error(function: str) -> None:
        raise LockedBrowserExecutableLeaseError(
            f"{function} failed with Windows error {ctypes.get_last_error()}"
        )


class LockedBrowserExecutableLease:
    """Hold a deny-write/delete handle from snapshot through exact replay.

    This proves transaction file stability only. It does not claim that already
    mapped browser pages are identical to the launcher file after process start.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = _require_explicit_path(path)
        self._backend = None
        self._handle: int | None = None
        self._snapshot: BrowserExecutableSnapshot | None = None
        self._entered = False

    @property
    def closed(self) -> bool:
        return self._entered and self._handle is None

    @property
    def snapshot(self) -> BrowserExecutableSnapshot:
        if self._snapshot is None or self._handle is None:
            raise LockedBrowserExecutableLeaseError(
                "Browser executable lease is not active"
            )
        return self._snapshot

    def __enter__(self) -> BrowserExecutableSnapshot:
        if self._entered:
            raise LockedBrowserExecutableLeaseError(
                "Browser executable lease cannot be entered twice"
            )
        self._entered = True
        if not _IS_WINDOWS:
            raise LockedBrowserExecutableLeaseError(
                "Browser executable locking is supported only on Windows"
            )
        try:
            self._backend = _create_windows_browser_file_backend()
            self._handle = self._backend.open_read_locked(self._path)
            _require_same_final_path(
                self._path, self._backend.final_path(self._handle)
            )
            self._snapshot = snapshot_browser_executable(self._path)
            recheck_browser_executable(self._snapshot)
            return self._snapshot
        except BaseException as primary_error:
            self._close_after(primary_error)
            raise

    def __exit__(self, kind, value, traceback) -> bool:
        try:
            self.close()
        except LockedBrowserExecutableLeaseError as close_error:
            if value is None:
                raise
            value.add_note(
                "Browser executable lease close also failed: "
                f"{close_error}"
            )
        return False

    def close(self) -> None:
        if self._handle is None:
            return
        handle = self._handle
        self._backend.close(handle)
        self._handle = None

    def _close_after(self, primary_error: BaseException) -> None:
        try:
            self.close()
        except LockedBrowserExecutableLeaseError as close_error:
            primary_error.add_note(
                "Browser executable lease close also failed: "
                f"{close_error}"
            )


def _require_explicit_path(path: str | Path) -> Path:
    try:
        lexical = Path(path)
        absolute = Path(os.path.abspath(os.fspath(lexical)))
        if not lexical.is_absolute() or lexical != absolute:
            raise LockedBrowserExecutableLeaseError(
                "Browser executable path must be explicit and absolute"
            )
        return absolute
    except LockedBrowserExecutableLeaseError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise LockedBrowserExecutableLeaseError(
            "Browser executable path is invalid"
        ) from exc


def _require_same_final_path(expected: Path, actual: Path) -> None:
    expected_text = os.path.normcase(os.path.normpath(os.fspath(expected)))
    actual_text = os.path.normcase(os.path.normpath(os.fspath(actual)))
    if expected_text != actual_text:
        raise LockedBrowserExecutableLeaseError(
            "Opened browser executable final path differs from the explicit path"
        )


def _strip_windows_device_prefix(path: str) -> str:
    if path.startswith("\\\\?\\UNC\\"):
        return "\\\\" + path[8:]
    if path.startswith("\\\\?\\"):
        return path[4:]
    return path


def _create_windows_browser_file_backend() -> _WindowsBrowserFileBackend:
    try:
        return _WindowsBrowserFileBackend()
    except (AttributeError, OSError) as exc:
        raise LockedBrowserExecutableLeaseError(
            "Windows browser executable locking APIs are unavailable"
        ) from exc
