"""Fail-closed temporary browser-profile ownership."""

from __future__ import annotations

from pathlib import Path
import tempfile
from types import TracebackType


MAX_CLEANUP_ATTEMPTS = 2


class BodySwayBrowserProfileLeaseError(RuntimeError):
    """Raised when a capture profile cannot be removed exactly."""


class BodySwayBrowserProfileLease:
    """Provide one fresh profile and preserve capture errors during cleanup."""

    def __init__(self) -> None:
        self._temporary = tempfile.TemporaryDirectory(
            prefix="autospine-body-sway-profile-"
        )
        # Windows can spell the process temp directory with an 8.3 segment
        # such as ``ADMINI~1``.  Canonicalize the directory we just created so
        # downstream browser guards receive one stable absolute path.
        self._path = Path(self._temporary.name).resolve(strict=True)
        self._entered = False

    def __enter__(self) -> Path:
        if self._entered:
            raise BodySwayBrowserProfileLeaseError(
                "Browser profile lease cannot be reused"
            )
        if not self._path.is_dir():
            raise BodySwayBrowserProfileLeaseError(
                "Fresh browser profile directory is unavailable"
            )
        self._entered = True
        return self._path

    def __exit__(
        self,
        kind: type[BaseException] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        cleanup_errors: list[BaseException] = []
        for _attempt in range(MAX_CLEANUP_ATTEMPTS):
            try:
                self._temporary.cleanup()
            except BaseException as exc:  # preserve the capture exception
                cleanup_errors.append(exc)
            if not self._path.exists():
                return False
        cleanup_error = BodySwayBrowserProfileLeaseError(
            "Browser profile was not removed after bounded cleanup retries"
        )
        for failure in cleanup_errors:
            cleanup_error.add_note(f"Profile cleanup attempt failed: {failure}")
        if value is None:
            if cleanup_errors:
                raise cleanup_error from cleanup_errors[-1]
            raise cleanup_error
        value.add_note(
            f"Browser profile cleanup also failed: {cleanup_error}"
        )
        for note in getattr(cleanup_error, "__notes__", ()):
            value.add_note(note)
        return False
