"""Resume the sole primary thread of a CREATE_SUSPENDED process."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import operator
import os
from typing import Any


TH32CS_SNAPTHREAD = 0x00000004
THREAD_SUSPEND_RESUME = 0x0002
ERROR_NO_MORE_FILES = 18
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_IS_WINDOWS = os.name == "nt"


class WindowsSuspendedProcessError(RuntimeError):
    """Raised when suspended-process ownership cannot be resumed exactly."""


class _ThreadEntry32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ThreadID", wintypes.DWORD),
        ("th32OwnerProcessID", wintypes.DWORD),
        ("tpBasePri", wintypes.LONG),
        ("tpDeltaPri", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
    ]


class _WindowsThreadBackend:
    def __init__(self) -> None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._snapshot = kernel32.CreateToolhelp32Snapshot
        self._snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        self._snapshot.restype = wintypes.HANDLE
        self._first = kernel32.Thread32First
        self._first.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(_ThreadEntry32),
        ]
        self._first.restype = wintypes.BOOL
        self._next = kernel32.Thread32Next
        self._next.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(_ThreadEntry32),
        ]
        self._next.restype = wintypes.BOOL
        self._open_thread = kernel32.OpenThread
        self._open_thread.argtypes = [
            wintypes.DWORD, wintypes.BOOL, wintypes.DWORD,
        ]
        self._open_thread.restype = wintypes.HANDLE
        self._resume = kernel32.ResumeThread
        self._resume.argtypes = [wintypes.HANDLE]
        self._resume.restype = wintypes.DWORD
        self._close = kernel32.CloseHandle
        self._close.argtypes = [wintypes.HANDLE]
        self._close.restype = wintypes.BOOL

    def owned_thread_ids(self, process_id: int) -> tuple[int, ...]:
        snapshot = self._snapshot(TH32CS_SNAPTHREAD, 0)
        if not snapshot or operator.index(snapshot) == INVALID_HANDLE_VALUE:
            self._raise_api_error("CreateToolhelp32Snapshot")
        primary_error: BaseException | None = None
        try:
            return self._read_owned_thread_ids(snapshot, process_id)
        except BaseException as exc:
            primary_error = exc
            raise
        finally:
            if not self._close(snapshot):
                close_error = WindowsSuspendedProcessError(
                    "CloseHandle(snapshot) failed with Windows error "
                    f"{ctypes.get_last_error()}"
                )
                if primary_error is None:
                    raise close_error
                primary_error.add_note(str(close_error))

    def _read_owned_thread_ids(
        self, snapshot: int, process_id: int
    ) -> tuple[int, ...]:
        entry = _ThreadEntry32()
        entry.dwSize = ctypes.sizeof(entry)
        if not self._first(snapshot, ctypes.byref(entry)):
            code = ctypes.get_last_error()
            if code == ERROR_NO_MORE_FILES:
                return ()
            self._raise_api_error("Thread32First")
        result = []
        while True:
            if entry.th32OwnerProcessID == process_id:
                result.append(int(entry.th32ThreadID))
            if self._next(snapshot, ctypes.byref(entry)):
                continue
            code = ctypes.get_last_error()
            if code != ERROR_NO_MORE_FILES:
                self._raise_api_error("Thread32Next")
            return tuple(result)

    def resume_once(self, thread_id: int) -> int:
        handle = self._open_thread(THREAD_SUSPEND_RESUME, False, thread_id)
        if not handle:
            self._raise_api_error("OpenThread")
        primary_error: BaseException | None = None
        try:
            previous_count = int(self._resume(handle))
            if previous_count == 0xFFFFFFFF:
                self._raise_api_error("ResumeThread")
            return previous_count
        except BaseException as exc:
            primary_error = exc
            raise
        finally:
            if not self._close(handle):
                close_error = WindowsSuspendedProcessError(
                    "CloseHandle(thread) failed with Windows error "
                    f"{ctypes.get_last_error()}"
                )
                if primary_error is None:
                    raise close_error
                primary_error.add_note(str(close_error))

    @staticmethod
    def _raise_api_error(function: str) -> None:
        raise WindowsSuspendedProcessError(
            f"{function} failed with Windows error {ctypes.get_last_error()}"
        )


def resume_suspended_primary_thread(process: Any) -> None:
    """Resume exactly one primary thread after Job Object assignment."""

    if not _IS_WINDOWS:
        return
    try:
        process_id = operator.index(process.pid)
        if process_id <= 0:
            raise ValueError("invalid process id")
    except (AttributeError, TypeError, ValueError) as exc:
        raise WindowsSuspendedProcessError(
            "Suspended browser has no valid process id"
        ) from exc
    backend = _create_windows_thread_backend()
    thread_ids = backend.owned_thread_ids(process_id)
    if len(thread_ids) != 1:
        raise WindowsSuspendedProcessError(
            "Suspended browser must have exactly one primary thread"
        )
    previous_count = backend.resume_once(thread_ids[0])
    if previous_count != 1:
        raise WindowsSuspendedProcessError(
            "Browser primary thread did not have the exact suspended state"
        )


def _create_windows_thread_backend() -> _WindowsThreadBackend:
    try:
        return _WindowsThreadBackend()
    except (AttributeError, OSError) as exc:
        raise WindowsSuspendedProcessError(
            "Windows thread snapshot APIs are unavailable"
        ) from exc
