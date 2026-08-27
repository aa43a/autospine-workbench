"""Hardened single-artifact Chromium driver for P10.7b captures."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
import threading
import time
from urllib.parse import quote, urlsplit

from .body_sway_headless_browser_output import (
    close_browser_output,
    raise_or_note_cleanup,
    read_bounded_browser_output,
)
from .browser_executable_snapshot import BrowserExecutableSnapshot
from .http_security import is_loopback_host
from .process_tree_cleanup import stop_owned_process_tree
from .spine42_v3_runtime_profile import BROWSER_FIXED_ARGUMENTS
from .windows_process_image import verify_suspended_browser_image
from .windows_process_job import (
    WindowsProcessJobError,
    attach_kill_on_close_process_job,
)
from .windows_suspended_process import resume_suspended_primary_thread


MAX_BROWSER_OUTPUT_BYTES = 64 * 1024
CAPTURE_TIMEOUT_SECONDS = 35.0
POLL_SECONDS = 0.02
GRACE_SECONDS = 1.0


class Spine42V3HeadlessBrowserError(RuntimeError):
    """Raised unless one browser process posts its exact artifact."""


def run_spine42_v3_headless_capture(
    browser: BrowserExecutableSnapshot,
    url: str,
    profile_directory: Path,
    collector,
    artifact_id: str,
) -> None:
    """Launch one isolated browser and wait for one terminal collector row."""

    _require_inputs(browser, url, profile_directory, collector, artifact_id)
    command = [
        browser.path,
        *BROWSER_FIXED_ARGUMENTS,
        f"--user-data-dir={profile_directory}",
        url,
    ]
    process = job = reader = None
    overflow, failed = threading.Event(), threading.Event()
    primary: BaseException | None = None
    close_failed = False
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
        job = attach_kill_on_close_process_job(process)
        verify_suspended_browser_image(process, browser)
        resume_suspended_primary_thread(process)
        if process.stdout is None:  # pragma: no cover
            raise Spine42V3HeadlessBrowserError(
                "Headless browser output pipe is unavailable"
            )
        reader = threading.Thread(
            target=read_bounded_browser_output,
            args=(process, overflow, failed, MAX_BROWSER_OUTPUT_BYTES),
            name=f"autospine-v3-runtime-{artifact_id}",
            daemon=True,
        )
        reader.start()
        _wait_for_terminal(
            process, collector, artifact_id, overflow, failed
        )
    except Spine42V3HeadlessBrowserError as exc:
        primary = exc
        raise
    except BaseException as exc:
        primary = Spine42V3HeadlessBrowserError(
            "Headless browser process could not complete safely"
        )
        raise primary from exc
    finally:
        cleanup = None
        try:
            stop_owned_process_tree(
                process, job, GRACE_SECONDS, GRACE_SECONDS
            )
        except WindowsProcessJobError as exc:
            cleanup = Spine42V3HeadlessBrowserError(
                f"Headless browser process cleanup failed: {exc}"
            )
        if reader is not None:
            reader.join(GRACE_SECONDS)
            if reader.is_alive():
                close_failed = not close_browser_output(process)
                reader.join(GRACE_SECONDS)
        close_failed = not close_browser_output(process) or close_failed
        if cleanup is not None:
            raise_or_note_cleanup(primary, cleanup)
        if overflow.is_set():
            raise_or_note_cleanup(primary, Spine42V3HeadlessBrowserError(
                "Headless browser output exceeded its byte limit"
            ))
        if close_failed or failed.is_set() or (
            reader is not None and reader.is_alive()
        ):
            raise_or_note_cleanup(primary, Spine42V3HeadlessBrowserError(
                "Headless browser output could not be closed"
            ))


def _wait_for_terminal(process, collector, artifact_id, overflow, failed):
    deadline = time.monotonic() + CAPTURE_TIMEOUT_SECONDS
    while True:
        captured, runtime_error = _terminal(collector, artifact_id)
        if overflow.is_set() or failed.is_set():
            raise Spine42V3HeadlessBrowserError(
                "Headless browser output could not be read safely"
            )
        if runtime_error:
            raise Spine42V3HeadlessBrowserError(
                "Official runtime reported a capture error"
            )
        code = process.poll()
        if code not in (None, 0):
            raise Spine42V3HeadlessBrowserError(
                f"Headless browser exited with status {code}"
            )
        if captured:
            return
        if code is not None:
            raise Spine42V3HeadlessBrowserError(
                "Browser exited without posting the exact artifact"
            )
        if time.monotonic() >= deadline:
            raise Spine42V3HeadlessBrowserError(
                "Official runtime capture timed out"
            )
        time.sleep(POLL_SECONDS)


def _require_inputs(browser, url, profile, collector, artifact_id) -> None:
    if type(browser) is not BrowserExecutableSnapshot:
        raise Spine42V3HeadlessBrowserError("Browser snapshot is invalid")
    ids = getattr(collector, "artifact_ids", ())
    if type(ids) is not tuple or artifact_id not in ids:
        raise Spine42V3HeadlessBrowserError("Artifact is absent from the plan")
    _fresh_profile(profile)
    try:
        parsed = urlsplit(url)
        expected = f"/capture/{quote(artifact_id, safe='')}"
        valid = parsed.scheme == "http" and parsed.hostname is not None \
            and is_loopback_host(parsed.hostname) and parsed.port is not None \
            and parsed.path == expected and not parsed.query \
            and not parsed.fragment and parsed.username is None \
            and parsed.password is None
    except (TypeError, ValueError) as exc:
        raise Spine42V3HeadlessBrowserError("Capture URL is invalid") from exc
    if not valid or _terminal(collector, artifact_id) != (False, False):
        raise Spine42V3HeadlessBrowserError(
            "Capture URL or collector state is invalid"
        )


def _terminal(collector, artifact_id) -> tuple[bool, bool]:
    try:
        status = collector.status()
        expected = {
            "expected_artifact_ids", "captured_artifact_ids",
            "error_artifact_ids", "complete",
        }
        if type(status) is not dict or set(status) != expected:
            raise TypeError("collector status shape differs")
        return (
            artifact_id in status["captured_artifact_ids"],
            artifact_id in status["error_artifact_ids"],
        )
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise Spine42V3HeadlessBrowserError(
            "Runtime collector status is invalid"
        ) from exc


def _fresh_profile(path: Path) -> None:
    try:
        absolute = Path(os.path.abspath(os.fspath(path)))
        metadata = absolute.lstat()
        if path != absolute or not path.is_absolute() \
                or not stat.S_ISDIR(metadata.st_mode) \
                or _alias(absolute, metadata) \
                or absolute.resolve(strict=True) != absolute \
                or next(absolute.iterdir(), None) is not None:
            raise Spine42V3HeadlessBrowserError(
                "Browser profile must be a fresh real absolute directory"
            )
        for parent in absolute.parents:
            parent_metadata = parent.lstat()
            if _alias(parent, parent_metadata) \
                    or not stat.S_ISDIR(parent_metadata.st_mode):
                raise Spine42V3HeadlessBrowserError(
                    "Browser profile parent is unsafe"
                )
    except Spine42V3HeadlessBrowserError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise Spine42V3HeadlessBrowserError(
            "Browser profile cannot be inspected"
        ) from exc


def _alias(path: Path, metadata: os.stat_result) -> bool:
    junction = getattr(path, "is_junction", None)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(metadata.st_mode) or (
        callable(junction) and junction()
    ) or bool(getattr(metadata, "st_file_attributes", 0) & reparse)


def _hidden_window_options() -> dict:
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    if os.name == "nt":
        flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
        flags |= getattr(subprocess, "CREATE_SUSPENDED", 0x00000004)
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        return {"creationflags": flags, "startupinfo": startup}
    return {"creationflags": flags}


__all__ = [
    "Spine42V3HeadlessBrowserError", "run_spine42_v3_headless_capture",
]
