"""Bounded cleanup for a Job-owned tree or a standalone root process."""

from __future__ import annotations

import subprocess
from typing import Any

from .windows_process_job import (
    KillOnCloseProcessJob,
    WindowsProcessJobError,
)


def stop_owned_process_tree(
    process: Any,
    job: KillOnCloseProcessJob | None,
    terminate_grace_seconds: float,
    kill_grace_seconds: float,
) -> None:
    """Close an owned job, or bound root cleanup on non-Windows systems."""

    if process is None:
        return
    if job is not None and job.owns_windows_process_tree:
        try:
            job.close()
            process.wait(timeout=kill_grace_seconds)
            return
        except subprocess.TimeoutExpired:
            # Closing a KILL_ON_JOB_CLOSE handle has already issued the
            # process-tree termination.  The root handle can nevertheless
            # remain signalled late while Chromium finishes Windows teardown.
            # A successful bounded root kill/wait is a complete recovery, not
            # evidence that capture itself failed.
            _force_stop_root(process, kill_grace_seconds)
            return
        except WindowsProcessJobError as close_error:
            _best_effort_stop_root(
                process, terminate_grace_seconds, kill_grace_seconds
            )
            try:
                job.close()
            except WindowsProcessJobError as retry_error:
                close_error.add_note(
                    f"Job handle close retry also failed: {retry_error}"
                )
            raise
        except (OSError, ValueError) as exc:
            raise WindowsProcessJobError(
                "Browser could not be waited after Job Object close"
            ) from exc
    _stop_root(process, terminate_grace_seconds, kill_grace_seconds)


def _stop_root(process: Any, terminate_grace: float, kill_grace: float) -> None:
    try:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=terminate_grace)
        except subprocess.TimeoutExpired:
            _force_stop_root(process, kill_grace)
    except WindowsProcessJobError:
        raise
    except (OSError, ValueError) as exc:
        raise WindowsProcessJobError(
            "Browser root-process cleanup failed"
        ) from exc


def _force_stop_root(process: Any, kill_grace: float) -> None:
    try:
        process.kill()
        process.wait(timeout=kill_grace)
    except subprocess.TimeoutExpired as exc:
        raise WindowsProcessJobError(
            "Browser root process could not be stopped"
        ) from exc
    except (OSError, ValueError) as exc:
        raise WindowsProcessJobError(
            "Browser root-process cleanup failed"
        ) from exc


def _best_effort_stop_root(
    process: Any, terminate_grace: float, kill_grace: float
) -> None:
    try:
        _stop_root(process, terminate_grace, kill_grace)
    except WindowsProcessJobError:
        pass
