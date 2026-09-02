"""Exact v2 type boundary for the frozen Spine v3 browser driver."""

from __future__ import annotations

from pathlib import Path

from .browser_executable_snapshot import BrowserExecutableSnapshot
from .spine42_v3_headless_browser import (
    Spine42V3HeadlessBrowserError,
    run_spine42_v3_headless_capture,
)
from .spine42_v3_runtime_capture_collector_v2 import (
    Spine42V3RuntimeCaptureCollectorV2,
)


class Spine42V3HeadlessBrowserV2Error(RuntimeError):
    """Raised when an exact v2 capture cannot complete safely."""


def run_spine42_v3_headless_capture_v2(
    browser: BrowserExecutableSnapshot,
    url: str,
    profile_directory: Path,
    collector: Spine42V3RuntimeCaptureCollectorV2,
    artifact_id: str,
) -> None:
    """Run the hardened process driver for one exact v2 collector row."""

    if type(browser) is not BrowserExecutableSnapshot:
        raise Spine42V3HeadlessBrowserV2Error(
            "Browser snapshot v2 input is invalid"
        )
    if type(collector) is not Spine42V3RuntimeCaptureCollectorV2:
        raise Spine42V3HeadlessBrowserV2Error(
            "Headless capture requires an exact runtime collector v2"
        )
    try:
        run_spine42_v3_headless_capture(
            browser, url, profile_directory, collector, artifact_id,
        )
    except Spine42V3HeadlessBrowserError as exc:
        mapped = Spine42V3HeadlessBrowserV2Error(str(exc))
        for note in getattr(exc, "__notes__", ()):
            mapped.add_note(note)
        raise mapped from exc


__all__ = [
    "Spine42V3HeadlessBrowserV2Error",
    "run_spine42_v3_headless_capture_v2",
]
