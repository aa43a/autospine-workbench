"""Collector-terminal Chrome driver for P10.3 Preview v2 captures."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import threading
import time
from typing import Any

from .body_sway_headless_browser_inputs import (
    BodySwayHeadlessBrowserError,
    collector_case_terminal_state,
    require_headless_capture_inputs,
)
from .body_sway_headless_browser_output import (
    close_browser_output,
    raise_or_note_cleanup,
    read_bounded_browser_output,
)
from .body_sway_runtime_capture_collector import (
    BodySwayRuntimeCaptureCollector,
)
from .body_sway_runtime_execution_profile import BROWSER_FIXED_ARGUMENTS
from .browser_executable_snapshot import BrowserExecutableSnapshot
from .process_tree_cleanup import stop_owned_process_tree
from .windows_process_image import (
    WindowsProcessImageError,
    verify_suspended_browser_image,
)
from .windows_process_job import (
    WindowsProcessJobError,
    attach_kill_on_close_process_job,
)
from .windows_suspended_process import (
    WindowsSuspendedProcessError,
    resume_suspended_primary_thread,
)


MAX_BROWSER_OUTPUT_BYTES = 64 * 1024
CAPTURE_TIMEOUT_SECONDS = 35.0
TERMINATE_GRACE_SECONDS = 1.0
KILL_GRACE_SECONDS = 1.0
POLL_SECONDS = 0.02


def run_body_sway_headless_capture_case(
    browser: BrowserExecutableSnapshot,
    url: str,
    profile_directory: Path,
    collector: BodySwayRuntimeCaptureCollector,
    case_id: str,
) -> None:
    """Run one v2 case until its exact collector callback is committed."""

    require_headless_capture_inputs(
        browser, url, profile_directory, collector, case_id,
    )
    command = [
        browser.path,
        *BROWSER_FIXED_ARGUMENTS,
        f"--user-data-dir={profile_directory}",
        url,
    ]
    process = process_job = output_reader = None
    output_overflow, output_failed = threading.Event(), threading.Event()
    output_close_failed = False
    capture_committed = False
    primary_error: BaseException | None = None
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=False,
            cwd=str(Path(browser.path).parent),
            close_fds=True,
            **_hidden_window_options(),
        )
        process_job = attach_kill_on_close_process_job(process)
        verify_suspended_browser_image(process, browser)
        resume_suspended_primary_thread(process)
        if process.stdout is None:  # pragma: no cover - guaranteed by PIPE
            raise BodySwayHeadlessBrowserError(
                "Headless browser output pipe is unavailable"
            )
        output_reader = threading.Thread(
            target=read_bounded_browser_output,
            args=(
                process, output_overflow, output_failed,
                MAX_BROWSER_OUTPUT_BYTES,
            ),
            name=f"autospine-browser-v2-output-{case_id}",
            daemon=True,
        )
        output_reader.start()
        deadline = time.monotonic() + CAPTURE_TIMEOUT_SECONDS
        while True:
            captured, runtime_error = collector_case_terminal_state(
                collector, case_id,
            )
            if output_overflow.is_set():
                raise BodySwayHeadlessBrowserError(
                    "Headless browser output exceeded its byte limit"
                )
            if runtime_error:
                raise BodySwayHeadlessBrowserError(
                    "Official runtime reported a terminal capture error"
                )
            return_code = process.poll()
            if return_code not in (None, 0):
                raise BodySwayHeadlessBrowserError(
                    "Headless browser exited with non-zero status "
                    f"{return_code}"
                )
            if captured:
                capture_committed = True
                return
            if output_failed.is_set():
                raise BodySwayHeadlessBrowserError(
                    "Headless browser output could not be read"
                )
            if return_code is not None:
                raise BodySwayHeadlessBrowserError(
                    "Headless browser exited without posting the exact capture"
                )
            if time.monotonic() >= deadline:
                raise BodySwayHeadlessBrowserError(
                    "Headless browser capture timed out"
                )
            time.sleep(POLL_SECONDS)
    except BodySwayHeadlessBrowserError as exc:
        primary_error = exc
        raise
    except OSError as exc:
        primary_error = BodySwayHeadlessBrowserError(
            "Headless browser could not be started or monitored"
        )
        raise primary_error from exc
    except (
        WindowsProcessImageError,
        WindowsProcessJobError,
        WindowsSuspendedProcessError,
    ) as exc:
        primary_error = BodySwayHeadlessBrowserError(
            f"Headless browser process-tree isolation failed: {exc}"
        )
        raise primary_error from exc
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        cleanup_error = _stop_process(process, process_job)
        if output_reader is not None:
            output_reader.join(KILL_GRACE_SECONDS)
            if output_reader.is_alive():
                output_close_failed = not close_browser_output(process)
                output_reader.join(KILL_GRACE_SECONDS)
        output_close_failed = (
            not close_browser_output(process) or output_close_failed
        )
        if cleanup_error is not None:
            raise_or_note_cleanup(primary_error, cleanup_error)
        if output_overflow.is_set():
            raise_or_note_cleanup(
                primary_error,
                BodySwayHeadlessBrowserError(
                    "Headless browser output exceeded its byte limit"
                ),
            )
        # Closing the owned Job is the declared v2 page lifetime.  A pipe read
        # can race that intentional close on Windows and report OSError even
        # after the exact PNG callback is committed.  Pre-commit read failures,
        # overflow, a live reader, or an uncloseable pipe remain fail-closed.
        if output_close_failed or (
            output_failed.is_set() and not capture_committed
        ) or (output_reader is not None and output_reader.is_alive()):
            raise_or_note_cleanup(
                primary_error,
                BodySwayHeadlessBrowserError(
                    "Headless browser output could not be read"
                ),
            )


def _stop_process(process, process_job) -> BodySwayHeadlessBrowserError | None:
    try:
        stop_owned_process_tree(
            process, process_job,
            TERMINATE_GRACE_SECONDS, KILL_GRACE_SECONDS,
        )
        return None
    except WindowsProcessJobError as exc:
        result = BodySwayHeadlessBrowserError(
            f"Headless browser process-tree cleanup failed: {exc}"
        )
        for note in getattr(exc, "__notes__", ()):
            result.add_note(note)
        return result


def _hidden_window_options() -> dict[str, Any]:
    creation_flags = (
        getattr(subprocess, "CREATE_NO_WINDOW", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    )
    if os.name == "nt":
        creation_flags |= getattr(subprocess, "CREATE_SUSPENDED", 0x00000004)
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        options: dict[str, Any] = {"startupinfo": startup}
    else:
        options = {}
    options["creationflags"] = creation_flags
    return options


__all__ = [
    "BodySwayHeadlessBrowserError",
    "run_body_sway_headless_capture_case",
]
