"""Allowlisted, read-only discovery for the P10 official-runtime environment."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any

from .browser_executable_snapshot import (
    BrowserExecutableSnapshot,
    BrowserExecutableSnapshotError,
    snapshot_browser_executable,
)
from .spine42_contract import SPINE_RUNTIME_PACKAGE, SPINE_RUNTIME_VERSION
from .spine42_runtime_inputs import (
    Spine42RuntimeInputError,
    Spine42RuntimePackage,
    require_runtime_package,
)


FORMAT = "autospine-p10-runtime-environment"
FORMAT_VERSION = 1
RUNTIME_RELATIVE_PATH = Path(
    "runtime/spine-player-4.2.119/node_modules/"
    "@esotericsoftware/spine-player"
)
WINDOWS_STANDARD_CHROME_PATHS = (
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
)


class P10RuntimeEnvironmentError(ValueError):
    """Raised only when the trusted state-root argument is malformed."""


@dataclass(frozen=True, slots=True)
class P10RuntimeEnvironment:
    """Private exact snapshots with a deliberately path-free projection."""

    runtime: Spine42RuntimePackage | None
    browser: BrowserExecutableSnapshot | None

    @property
    def available(self) -> bool:
        return self.runtime is not None and self.browser is not None

    def public_document(self) -> dict[str, Any]:
        """Return bounded identities; local paths and authorization are absent."""

        runtime = self.runtime
        browser = self.browser
        return _copy({
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "available": self.available,
            "runtime": {
                "available": runtime is not None,
                "package": SPINE_RUNTIME_PACKAGE,
                "version": SPINE_RUNTIME_VERSION,
                "javascript_sha256": (
                    runtime.javascript_sha256 if runtime is not None else None
                ),
                "stylesheet_sha256": (
                    runtime.stylesheet_sha256 if runtime is not None else None
                ),
                "package_json_sha256": (
                    runtime.package_json_sha256 if runtime is not None else None
                ),
                "license_sha256": (
                    runtime.license_sha256 if runtime is not None else None
                ),
                "license_acknowledged": False,
                "license_file_presence_is_authorization": False,
            },
            "browser": {
                "available": browser is not None,
                "family": browser.family if browser is not None else None,
                "reported_version": (
                    browser.reported_version if browser is not None else None
                ),
                "executable_sha256": (
                    browser.executable_sha256 if browser is not None else None
                ),
                "size_bytes": (
                    browser.size_bytes if browser is not None else None
                ),
            },
        })


def discover_p10_runtime_environment(
    state_root: Path,
) -> P10RuntimeEnvironment:
    """Inspect only the pinned state-root runtime and standard Chrome paths.

    Discovery never downloads, starts, or captures anything.  Invalid candidates
    are treated as unavailable so a caller cannot accidentally use unverified
    adjacent bytes.
    """

    root = _state_root(state_root)
    runtime = _discover_runtime(root / RUNTIME_RELATIVE_PATH)
    browser = _discover_browser()
    return P10RuntimeEnvironment(runtime, browser)


def _discover_runtime(path: Path) -> Spine42RuntimePackage | None:
    try:
        return require_runtime_package(path)
    except (OSError, Spine42RuntimeInputError, TypeError, ValueError):
        return None


def _discover_browser() -> BrowserExecutableSnapshot | None:
    if not _windows_host():
        return None
    for path in WINDOWS_STANDARD_CHROME_PATHS:
        try:
            if not path.is_file():
                continue
            return snapshot_browser_executable(path)
        except (
            BrowserExecutableSnapshotError, OSError, RuntimeError,
            TypeError, ValueError,
        ):
            continue
    return None


def _state_root(value: Path) -> Path:
    try:
        return Path(os.path.abspath(os.fspath(Path(value))))
    except (OSError, TypeError, ValueError) as exc:
        raise P10RuntimeEnvironmentError(
            "P10 runtime environment state root is invalid"
        ) from exc


def _windows_host() -> bool:
    return os.name == "nt"


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))


__all__ = [
    "FORMAT", "FORMAT_VERSION", "P10RuntimeEnvironment",
    "P10RuntimeEnvironmentError", "RUNTIME_RELATIVE_PATH",
    "WINDOWS_STANDARD_CHROME_PATHS", "discover_p10_runtime_environment",
]
