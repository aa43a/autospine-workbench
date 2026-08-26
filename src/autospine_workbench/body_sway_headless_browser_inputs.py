"""Fail-closed input validation for one headless capture case."""

from __future__ import annotations

import os
from pathlib import Path
import stat
from urllib.parse import quote, urlsplit

from .body_sway_runtime_capture_collector import (
    BodySwayRuntimeCaptureCollector,
)
from .browser_executable_snapshot import BrowserExecutableSnapshot
from .http_security import is_loopback_host


class BodySwayHeadlessBrowserError(RuntimeError):
    """Raised unless one browser invocation posts its exact case capture."""


def require_headless_capture_inputs(
    browser: BrowserExecutableSnapshot,
    url: str,
    profile: Path,
    collector: BodySwayRuntimeCaptureCollector,
    case_id: str,
) -> None:
    if type(browser) is not BrowserExecutableSnapshot:
        raise BodySwayHeadlessBrowserError(
            "Headless capture requires an exact browser snapshot"
        )
    if type(collector) is not BodySwayRuntimeCaptureCollector:
        raise BodySwayHeadlessBrowserError(
            "Headless capture requires the exact runtime collector"
        )
    if type(case_id) is not str or case_id not in collector.case_ids:
        raise BodySwayHeadlessBrowserError(
            "Headless capture case is absent from the exact plan"
        )
    _require_fresh_profile(profile)
    _require_case_url(url, case_id)
    captured, runtime_error = collector_case_terminal_state(
        collector, case_id
    )
    if captured or runtime_error:
        raise BodySwayHeadlessBrowserError(
            "Headless capture case already has a terminal result"
        )


def collector_case_terminal_state(
    collector: BodySwayRuntimeCaptureCollector, case_id: str
) -> tuple[bool, bool]:
    try:
        status = collector.status()
        captured = status["captured_case_ids"]
        errors = status["error_case_ids"]
        if type(captured) is not list or type(errors) is not list:
            raise TypeError("terminal case lists are invalid")
        return case_id in captured, case_id in errors
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise BodySwayHeadlessBrowserError(
            "Runtime collector status is invalid"
        ) from exc


def _require_fresh_profile(value: Path) -> None:
    try:
        if not isinstance(value, Path) or not value.is_absolute():
            raise BodySwayHeadlessBrowserError(
                "Browser profile directory must be an absolute Path"
            )
        lexical = Path(os.path.abspath(os.fspath(value)))
        metadata = lexical.lstat()
        if (
            value != lexical
            or _is_alias(lexical, metadata)
            or not stat.S_ISDIR(metadata.st_mode)
            or lexical.resolve(strict=True) != lexical
        ):
            raise BodySwayHeadlessBrowserError(
                "Browser profile directory must be real and unaliased"
            )
        for parent in lexical.parents:
            parent_metadata = parent.lstat()
            if _is_alias(parent, parent_metadata) or not stat.S_ISDIR(
                parent_metadata.st_mode
            ):
                raise BodySwayHeadlessBrowserError(
                    "Browser profile parent directories must be unaliased"
                )
        if next(lexical.iterdir(), None) is not None:
            raise BodySwayHeadlessBrowserError(
                "Browser profile directory must be fresh and empty"
            )
    except BodySwayHeadlessBrowserError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise BodySwayHeadlessBrowserError(
            "Browser profile directory cannot be inspected safely"
        ) from exc


def _require_case_url(value: str, case_id: str) -> None:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise BodySwayHeadlessBrowserError("Capture URL is invalid") from exc
    expected_path = f"/capture/{quote(case_id, safe='')}"
    if (
        type(value) is not str
        or parsed.scheme != "http"
        or not parsed.hostname
        or not is_loopback_host(parsed.hostname)
        or port is None
        or not 0 < port <= 65535
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path != expected_path
    ):
        raise BodySwayHeadlessBrowserError(
            "Capture URL must be the exact loopback case URL"
        )


def _is_alias(path: Path, metadata: os.stat_result) -> bool:
    junction = getattr(path, "is_junction", None)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return (
        stat.S_ISLNK(metadata.st_mode)
        or (callable(junction) and junction())
        or bool(getattr(metadata, "st_file_attributes", 0) & reparse)
    )
