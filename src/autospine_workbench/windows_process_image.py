"""Bind a suspended Windows process image to its expected browser snapshot."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import operator
import os
from pathlib import Path
from typing import Any

from .browser_executable_snapshot import (
    BrowserExecutableSnapshot,
    BrowserExecutableSnapshotError,
    recheck_browser_executable,
)


MAX_WINDOWS_IMAGE_PATH_CHARS = 32_768
_IS_WINDOWS = os.name == "nt"


class WindowsProcessImageError(RuntimeError):
    """Raised when the launched image cannot be bound to expected bytes."""


class _WindowsProcessImageBackend:
    def __init__(self) -> None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._query = kernel32.QueryFullProcessImageNameW
        self._query.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self._query.restype = wintypes.BOOL

    def query_path(self, process_handle: int) -> Path:
        buffer = ctypes.create_unicode_buffer(MAX_WINDOWS_IMAGE_PATH_CHARS)
        length = wintypes.DWORD(MAX_WINDOWS_IMAGE_PATH_CHARS)
        if not self._query(process_handle, 0, buffer, ctypes.byref(length)):
            raise WindowsProcessImageError(
                "QueryFullProcessImageNameW failed with Windows error "
                f"{ctypes.get_last_error()}"
            )
        if not 0 < length.value < MAX_WINDOWS_IMAGE_PATH_CHARS:
            raise WindowsProcessImageError(
                "Launched browser image path has an invalid length"
            )
        return Path(buffer.value)


def verify_suspended_browser_image(
    process: Any, expected: BrowserExecutableSnapshot
) -> None:
    """Verify mapped image path and rehash expected bytes before resume."""

    if type(expected) is not BrowserExecutableSnapshot:
        raise WindowsProcessImageError("Expected browser snapshot is invalid")
    if _IS_WINDOWS:
        process_handle = _require_process_handle(process)
        actual = _create_windows_process_image_backend().query_path(
            process_handle
        )
        try:
            expected_path = Path(expected.path)
            if actual.resolve(strict=True) != expected_path:
                raise WindowsProcessImageError(
                    "Launched browser image path differs from the explicit path"
                )
        except WindowsProcessImageError:
            raise
        except (OSError, RuntimeError, ValueError) as exc:
            raise WindowsProcessImageError(
                "Launched browser image path cannot be resolved safely"
            ) from exc
    try:
        recheck_browser_executable(expected)
    except BrowserExecutableSnapshotError as exc:
        raise WindowsProcessImageError(
            "Launched browser bytes changed before primary-thread resume"
        ) from exc


def _require_process_handle(process: Any) -> int:
    try:
        handle = operator.index(process._handle)
        if handle <= 0:
            raise ValueError("invalid process handle")
        return handle
    except (AttributeError, TypeError, ValueError) as exc:
        raise WindowsProcessImageError(
            "Suspended browser has no valid Windows process handle"
        ) from exc


def _create_windows_process_image_backend() -> _WindowsProcessImageBackend:
    try:
        return _WindowsProcessImageBackend()
    except (AttributeError, OSError) as exc:
        raise WindowsProcessImageError(
            "Windows process-image APIs are unavailable"
        ) from exc
