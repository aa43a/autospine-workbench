"""Fail-closed Windows process-tree ownership via a Job Object."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import operator
import os
from typing import Any


JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
ERROR_ACCESS_DENIED = 5
_IS_WINDOWS = os.name == "nt"


class WindowsProcessJobError(RuntimeError):
    """Raised when Windows process-tree ownership cannot be proven."""


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _WindowsJobBackend:
    def __init__(self) -> None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._create = kernel32.CreateJobObjectW
        self._create.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self._create.restype = wintypes.HANDLE
        self._set_information = kernel32.SetInformationJobObject
        self._set_information.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ]
        self._set_information.restype = wintypes.BOOL
        self._is_process_in_job = kernel32.IsProcessInJob
        self._is_process_in_job.argtypes = [
            wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL),
        ]
        self._is_process_in_job.restype = wintypes.BOOL
        self._assign = kernel32.AssignProcessToJobObject
        self._assign.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self._assign.restype = wintypes.BOOL
        self._close = kernel32.CloseHandle
        self._close.argtypes = [wintypes.HANDLE]
        self._close.restype = wintypes.BOOL

    def create(self) -> int:
        handle = self._create(None, None)
        if not handle:
            self._raise_api_error("CreateJobObjectW")
        return operator.index(handle)

    def configure_kill_on_close(self, handle: int) -> None:
        limits = _ExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = (
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
        succeeded = self._set_information(
            handle,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        )
        if not succeeded:
            self._raise_api_error("SetInformationJobObject")

    def process_is_in_job(
        self, process_handle: int, job_handle: int | None
    ) -> bool:
        result = wintypes.BOOL()
        if not self._is_process_in_job(
            process_handle, job_handle, ctypes.byref(result)
        ):
            self._raise_api_error("IsProcessInJob")
        return bool(result.value)

    def assign(self, handle: int, process_handle: int) -> None:
        if self._assign(handle, process_handle):
            return
        code = ctypes.get_last_error()
        if code == ERROR_ACCESS_DENIED:
            raise WindowsProcessJobError(
                "AssignProcessToJobObject denied nested inner-job assignment"
            )
        raise WindowsProcessJobError(
            f"AssignProcessToJobObject failed with Windows error {code}"
        )

    def close(self, handle: int) -> None:
        if not self._close(handle):
            self._raise_api_error("CloseHandle")

    @staticmethod
    def _raise_api_error(function: str) -> None:
        raise WindowsProcessJobError(
            f"{function} failed with Windows error {ctypes.get_last_error()}"
        )


@dataclass
class KillOnCloseProcessJob:
    """Owned job handle; closing it terminates the assigned process tree."""

    _handle: int | None
    _backend: Any | None

    @property
    def owns_windows_process_tree(self) -> bool:
        return self._handle is not None

    def close(self) -> None:
        if self._handle is None:
            return
        handle = self._handle
        self._backend.close(handle)
        self._handle = None


def attach_kill_on_close_process_job(process: Any) -> KillOnCloseProcessJob:
    """Immediately assign a live Popen process to a new kill-on-close job."""

    if not _IS_WINDOWS:
        return KillOnCloseProcessJob(None, None)
    process_handle = _require_live_process_handle(process)
    backend = _create_windows_job_backend()
    job_handle = backend.create()
    try:
        backend.configure_kill_on_close(job_handle)
        if process.poll() is not None:
            raise WindowsProcessJobError(
                "Browser exited before Job Object assignment"
            )
        backend.assign(job_handle, process_handle)
        if not backend.process_is_in_job(process_handle, job_handle):
            raise WindowsProcessJobError(
                "Browser inner Job Object membership could not be verified"
            )
    except BaseException as primary_error:
        for attempt in range(2):
            try:
                backend.close(job_handle)
                break
            except WindowsProcessJobError as close_error:
                primary_error.add_note(
                    f"Job handle close attempt {attempt + 1} also failed: "
                    f"{close_error}"
                )
        raise
    return KillOnCloseProcessJob(job_handle, backend)


def _require_live_process_handle(process: Any) -> int:
    try:
        if process.poll() is not None:
            raise WindowsProcessJobError(
                "Browser exited before Job Object assignment"
            )
        process_handle = operator.index(process._handle)
        if process_handle <= 0:
            raise ValueError("invalid process handle")
        return process_handle
    except WindowsProcessJobError:
        raise
    except (AttributeError, TypeError, ValueError) as exc:
        raise WindowsProcessJobError(
            "Browser process has no valid Windows process handle"
        ) from exc


def _create_windows_job_backend() -> _WindowsJobBackend:
    try:
        return _WindowsJobBackend()
    except (AttributeError, OSError) as exc:
        raise WindowsProcessJobError(
            "Windows Job Object APIs are unavailable"
        ) from exc
