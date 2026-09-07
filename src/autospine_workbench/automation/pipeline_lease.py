"""Crash-released per-run execution lease; cancel uses the journal CAS."""

from contextlib import contextmanager
import os
from pathlib import Path
import stat

from ..motion_instance_v3_staging_cleanup import is_alias
from ..spine42_v3_bundle_files import existing_exact_child
from .pipeline_run import PipelineRunError
from .pipeline_run_validation import require_run_id
from .storage_io import directory


@contextmanager
def execution_lease(state_root, run_id):
    require_run_id(run_id)
    parent = directory(Path(state_root) / "jobs" / "pipeline-execution-v1" / run_id, create=True)
    path = parent / "owner.lock"
    descriptor = None
    acquired = False
    try:
        existing_exact_child(parent, path.name)
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        descriptor = os.open(path, flags, 0o600)
        opened, linked = os.fstat(descriptor), path.lstat()
        if is_alias(path) or not stat.S_ISREG(linked.st_mode) or opened.st_nlink != 1 \
                or (opened.st_dev, opened.st_ino) != (linked.st_dev, linked.st_ino):
            raise PipelineRunError("pipeline_storage_invalid")
        # Lock byte zero, even for an empty lock file. Initialize only after acquiring.
        os.lseek(descriptor, 0, os.SEEK_SET)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        acquired = True
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"\0")
            os.fsync(descriptor)
    except PipelineRunError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise PipelineRunError("pipeline_run_busy") from exc
    try:
        yield
    finally:
        try:
            if acquired:
                os.lseek(descriptor, 0, os.SEEK_SET)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
