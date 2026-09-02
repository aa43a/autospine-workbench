"""Crash-released cross-process serialization for P10.7b v2 journals."""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import stat
import threading
import time

from .motion_instance_v3_staging_cleanup import is_alias
from .p10_spine42_v3_runtime_job_errors_v2 import (
    P10Spine42V3RuntimeJobStoreV2Error,
)
from .p10_spine42_v3_runtime_job_files_v2 import namespace
from .spine42_v3_bundle_files import require_real_directory

LOCK_NAMESPACE = "body-sway-spine42-v3-runtime-job-lock-v2"
_LOCK_NAME = "process.lock"
_WAIT_SECONDS = 15.0
_POLL_SECONDS = 0.02
_LOCAL = threading.local()


P10Spine42V3RuntimeJobProcessLockV2Error = \
    P10Spine42V3RuntimeJobStoreV2Error


@contextmanager
def runtime_job_process_lock_v2(root):
    """Hold one alias-safe OS lock; nested calls in one thread are reentrant."""
    parent = _lock_parent(root)
    key = os.path.normcase(os.path.abspath(os.fspath(parent)))
    held = getattr(_LOCAL, "held", {})
    record = held.get(key)
    if record is not None and record["pid"] == os.getpid():
        record["depth"] += 1
        try:
            yield
        finally:
            record["depth"] -= 1
        return
    descriptor = None
    acquired = False
    try:
        descriptor = _open_lock(parent)
        deadline = time.monotonic() + _WAIT_SECONDS
        while not _try_acquire(descriptor):
            if time.monotonic() >= deadline:
                raise P10Spine42V3RuntimeJobProcessLockV2Error(
                    "Runtime job writer lock timed out")
            time.sleep(_POLL_SECONDS)
        acquired = True
    except P10Spine42V3RuntimeJobProcessLockV2Error:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise P10Spine42V3RuntimeJobProcessLockV2Error(
            "Runtime job writer lock is unavailable") from exc
    held[key] = {"pid": os.getpid(), "depth": 1}
    _LOCAL.held = held
    try:
        yield
    finally:
        if acquired:
            held.pop(key, None)
            try:
                _release(descriptor)
            except OSError:
                pass
        if descriptor is not None:
            os.close(descriptor)


def _open_lock(parent):
    require_real_directory(parent, "Runtime job writer lock parent")
    children = list(parent.iterdir())
    if children and (len(children) != 1 or children[0].name != _LOCK_NAME):
        raise P10Spine42V3RuntimeJobProcessLockV2Error(
            "Runtime job writer lock inventory is unsafe")
    flags = os.O_RDWR | os.O_CREAT
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(parent / _LOCK_NAME, flags, 0o600)
    try:
        path_info = (parent / _LOCK_NAME).lstat()
        open_info = os.fstat(descriptor)
        if is_alias(parent / _LOCK_NAME) \
                or not stat.S_ISREG(path_info.st_mode) \
                or (path_info.st_dev, path_info.st_ino) \
                != (open_info.st_dev, open_info.st_ino) \
                or open_info.st_nlink != 1:
            raise P10Spine42V3RuntimeJobProcessLockV2Error(
                "Runtime job writer lock is unsafe")
        if open_info.st_size == 0:
            os.write(descriptor, b"\0")
            os.fsync(descriptor)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _lock_parent(root):
    try:
        return namespace(root, LOCK_NAMESPACE, create=True)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise P10Spine42V3RuntimeJobProcessLockV2Error(
            "Runtime job writer lock is unavailable") from exc


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
    "LOCK_NAMESPACE", "P10Spine42V3RuntimeJobProcessLockV2Error",
    "runtime_job_process_lock_v2",
]
