"""Opt-in lifetime containment for a Studio-owned Windows engine only."""
from dataclasses import dataclass
import ctypes
from ctypes import wintypes
import os

from .windows_process_job import _create_windows_job_backend


_IS_WINDOWS = os.name == 'nt'
_owned_lifetime = None
_failed_job = None


class StudioProcessLifetimeError(RuntimeError):
    """The engine must not start if its process tree cannot be contained."""


@dataclass(frozen=True)
class StudioProcessLifetime:
    """Retain the non-inheritable handle until OS process teardown.

    Intentionally has no close method: this process belongs to the job too,
    so closing its last handle while running would terminate the engine.
    """
    _handle: int | None
    _backend: object | None

    @property
    def owns_windows_process_tree(self):
        return self._handle is not None


def _current_process_and_noninheritable_job(job_handle):
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    current = api.GetCurrentProcess
    current.argtypes = []; current.restype = wintypes.HANDLE
    information = api.GetHandleInformation
    information.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    information.restype = wintypes.BOOL
    flags = wintypes.DWORD()
    if not information(job_handle, ctypes.byref(flags)) or flags.value & 1:
        raise StudioProcessLifetimeError('Studio engine Job Object handle is inheritable or unverifiable.')
    return current()


def keep_owned_process_tree():
    """Call before any worker is spawned; unused by external Workbench startup."""
    global _owned_lifetime, _failed_job
    if _failed_job is not None:
        raise StudioProcessLifetimeError('Studio engine process-tree membership remains unverified; startup must stop.')
    if _owned_lifetime is not None:
        return _owned_lifetime
    if not _IS_WINDOWS:
        return StudioProcessLifetime(None, None)
    backend, handle, assigned = None, None, False
    try:
        backend = _create_windows_job_backend()
        handle = backend.create()
        backend.configure_kill_on_close(handle)
        current = _current_process_and_noninheritable_job(handle)
        backend.assign(handle, current)
        assigned = True
        if not backend.process_is_in_job(current, handle):
            raise StudioProcessLifetimeError('Studio engine process-tree membership cannot be verified.')
        _owned_lifetime = StudioProcessLifetime(handle, backend)
        return _owned_lifetime
    except BaseException as exc:
        if handle is not None:
            if assigned:
                # Closing would terminate this process before its launcher can
                # report the failure. Retain until the failed startup exits.
                # Keep this separate from the verified owner. A subsequent
                # call must still fail rather than claiming containment.
                _failed_job = (handle, backend)
            else:
                try:
                    backend.close(handle)
                except BaseException as cleanup:
                    exc.add_note(f'Unassigned Studio job cleanup failed: {cleanup}')
        if isinstance(exc, StudioProcessLifetimeError):
            raise
        raise StudioProcessLifetimeError('Studio engine process-tree ownership failed.') from exc
