"""Bounded browser-output draining and cleanup error reporting."""

from __future__ import annotations

import threading
from typing import Any

from .body_sway_headless_browser_inputs import BodySwayHeadlessBrowserError


OUTPUT_CHUNK_BYTES = 4096


def read_bounded_browser_output(
    process: Any,
    overflow: threading.Event,
    failed: threading.Event,
    max_bytes: int,
) -> None:
    total = 0
    try:
        while chunk := process.stdout.read(OUTPUT_CHUNK_BYTES):
            total += len(chunk)
            if total > max_bytes:
                overflow.set()
                try:
                    process.kill()
                except OSError:
                    pass
                return
    except (OSError, ValueError):
        failed.set()


def close_browser_output(process: Any) -> bool:
    if (
        process is not None
        and process.stdout is not None
        and not process.stdout.closed
    ):
        try:
            process.stdout.close()
        except OSError:
            return False
    return True


def raise_or_note_cleanup(
    primary_error: BaseException | None,
    cleanup_error: BodySwayHeadlessBrowserError,
) -> None:
    if primary_error is None:
        raise cleanup_error
    primary_error.add_note(f"Cleanup also failed: {cleanup_error}")
    for note in getattr(cleanup_error, "__notes__", ()):
        primary_error.add_note(f"Cleanup detail: {note}")
