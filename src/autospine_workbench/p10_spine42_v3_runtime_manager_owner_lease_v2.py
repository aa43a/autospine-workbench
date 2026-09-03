"""Crash-released lifetime owner lease for one P10.7b v2 manager."""

from __future__ import annotations

import os
import stat
import threading

from .motion_instance_v3_staging_cleanup import is_alias
from .p10_spine42_v3_runtime_job_files_v2 import (
    namespace, normalized_state_root,
)
from .spine42_v3_bundle_files import require_real_directory

LOCK_NAMESPACE = "body-sway-spine42-v3-runtime-manager-owner-v2"
_LOCK_NAME = "owner.lock"
_PROCESS_GUARD = threading.Lock()
_PROCESS_HELD = {}


class P10Spine42V3RuntimeManagerOwnerLeaseV2Error(RuntimeError):
    """Path-free owner acquisition or release failure."""


class P10Spine42V3RuntimeManagerOwnerLeaseV2:
    """Hold an OS lock for the complete lifetime of one manager."""

    __slots__ = ("_root", "_descriptor", "_key", "_token")

    def __init__(self, state_root):
        try:
            self._root = normalized_state_root(state_root)
            self._descriptor = None
            self._key = None
            self._token = None
        except Exception as exc:
            raise P10Spine42V3RuntimeManagerOwnerLeaseV2Error(
                "Runtime manager owner lease is unavailable") from exc

    @property
    def acquired(self):
        return self._descriptor is not None

    def acquire(self):
        if self.acquired:
            return self
        descriptor = None
        try:
            parent = namespace(self._root, LOCK_NAMESPACE, create=True)
            key = os.path.normcase(os.path.abspath(os.fspath(parent)))
            with _PROCESS_GUARD:
                if key in _PROCESS_HELD:
                    raise P10Spine42V3RuntimeManagerOwnerLeaseV2Error(
                        "Another runtime manager owner is active")
                descriptor = _open_lock(parent)
                if not _try_acquire(descriptor):
                    raise P10Spine42V3RuntimeManagerOwnerLeaseV2Error(
                        "Another runtime manager owner is active")
                token = object()
                _PROCESS_HELD[key] = (descriptor, token)
                self._descriptor, self._key, self._token = (
                    descriptor, key, token,
                )
                descriptor = None
            return self
        except P10Spine42V3RuntimeManagerOwnerLeaseV2Error:
            if descriptor is not None:
                os.close(descriptor)
            raise
        except Exception as exc:
            if descriptor is not None:
                os.close(descriptor)
            raise P10Spine42V3RuntimeManagerOwnerLeaseV2Error(
                "Runtime manager owner lease could not be acquired") from exc

    def close(self):
        descriptor, key, token = (
            self._descriptor, self._key, self._token,
        )
        if descriptor is None:
            return
        self._descriptor = self._key = self._token = None
        failure = None
        with _PROCESS_GUARD:
            try:
                _release(descriptor)
            except OSError as exc:
                failure = exc
            finally:
                if _PROCESS_HELD.get(key) == (descriptor, token):
                    _PROCESS_HELD.pop(key)
                try:
                    os.close(descriptor)
                except OSError as exc:
                    failure = failure or exc
        if failure is not None:
            raise P10Spine42V3RuntimeManagerOwnerLeaseV2Error(
                "Runtime manager owner lease could not be released") from failure

    def __enter__(self):
        return self.acquire()

    def __exit__(self, _kind, _value, _traceback):
        self.close()

    def __reduce_ex__(self, _protocol):
        raise TypeError("Runtime manager owner lease cannot be serialized")


def _require_acquired_p10_spine42_v3_runtime_manager_owner_lease_v2(value):
    """Return an internal root/epoch identity only for the current owner."""
    try:
        if type(value) is not P10Spine42V3RuntimeManagerOwnerLeaseV2:
            raise ValueError
        with _PROCESS_GUARD:
            descriptor, key, token = (
                value._descriptor, value._key, value._token,
            )
            if type(descriptor) is not int or type(key) is not str \
                    or token is None \
                    or _PROCESS_HELD.get(key) != (descriptor, token):
                raise ValueError
            current = os.fstat(descriptor)
            if not stat.S_ISREG(current.st_mode) or current.st_nlink != 1:
                raise ValueError
            root = os.path.normcase(os.path.abspath(os.fspath(value._root)))
            return root, token
    except P10Spine42V3RuntimeManagerOwnerLeaseV2Error:
        raise
    except Exception as exc:
        raise P10Spine42V3RuntimeManagerOwnerLeaseV2Error(
            "Runtime manager owner lease is not active") from exc


def _open_lock(parent):
    require_real_directory(parent, "Runtime manager owner lock parent")
    children = list(parent.iterdir())
    if children and (len(children) != 1 or children[0].name != _LOCK_NAME):
        raise P10Spine42V3RuntimeManagerOwnerLeaseV2Error(
            "Runtime manager owner lock inventory is unsafe")
    path = parent / _LOCK_NAME
    flags = os.O_RDWR | os.O_CREAT
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        os.set_inheritable(descriptor, False)
        path_info, open_info = path.lstat(), os.fstat(descriptor)
        if is_alias(path) or not stat.S_ISREG(path_info.st_mode) \
                or (path_info.st_dev, path_info.st_ino) != (
                    open_info.st_dev, open_info.st_ino
                ) or open_info.st_nlink != 1:
            raise P10Spine42V3RuntimeManagerOwnerLeaseV2Error(
                "Runtime manager owner lock is unsafe")
        if open_info.st_size == 0:
            os.write(descriptor, b"\0")
            os.fsync(descriptor)
        final = os.fstat(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        if final.st_size != 1 or os.read(descriptor, 1) != b"\0":
            raise P10Spine42V3RuntimeManagerOwnerLeaseV2Error(
                "Runtime manager owner lock is unsafe")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _try_acquire(descriptor):
    os.lseek(descriptor, 0, os.SEEK_SET)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _release(descriptor):
    os.lseek(descriptor, 0, os.SEEK_SET)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(descriptor, fcntl.LOCK_UN)


__all__ = [
    "LOCK_NAMESPACE", "P10Spine42V3RuntimeManagerOwnerLeaseV2",
    "P10Spine42V3RuntimeManagerOwnerLeaseV2Error",
]
