"""Link-safe, bounded reads for local review evidence files."""

from __future__ import annotations

import os
from pathlib import Path
import stat


class BoundedReviewEvidenceError(ValueError):
    """Raised when local evidence escapes or changes across a bounded read."""


def path_is_linklike(path: Path) -> bool:
    """Return whether a path is a symlink or Windows junction."""

    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        return bool(is_junction and is_junction())
    except OSError as exc:
        raise BoundedReviewEvidenceError(
            "Automatic review package path is unreadable"
        ) from exc


def require_real_directory(path: Path) -> None:
    """Require one existing directory whose final component is not a link."""

    if path_is_linklike(path) or not path.is_dir():
        raise BoundedReviewEvidenceError(
            "Automatic review package directory is unsafe"
        )


def read_bounded_text(path: Path, maximum: int, root: Path) -> str:
    """Read one confined regular file once without following path links."""

    try:
        if maximum < 0 or path_is_linklike(path):
            raise BoundedReviewEvidenceError(
                "Review evidence is not a bounded file"
            )
        root_resolved = _resolved_real_directory(root)
        resolved = path.resolve(strict=True)
        if resolved != path.absolute():
            raise BoundedReviewEvidenceError("Review evidence path is unsafe")
        resolved.relative_to(root_resolved)
        before = resolved.lstat()
        if not stat.S_ISREG(before.st_mode):
            raise BoundedReviewEvidenceError(
                "Review evidence is not a bounded file"
            )
        with resolved.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if not os.path.samestat(before, opened) \
                    or not stat.S_ISREG(opened.st_mode) \
                    or opened.st_size > maximum:
                raise BoundedReviewEvidenceError(
                    "Review evidence is not a bounded file"
                )
            payload = stream.read(maximum + 1)
            after = os.fstat(stream.fileno())
            if not os.path.samestat(opened, after) \
                    or opened.st_size != after.st_size \
                    or opened.st_mtime_ns != after.st_mtime_ns:
                raise BoundedReviewEvidenceError(
                    "Review evidence changed while it was read"
                )
        if len(payload) > maximum:
            raise BoundedReviewEvidenceError(
                "Review evidence is not a bounded file"
            )
        return payload.decode("utf-8")
    except BoundedReviewEvidenceError:
        raise
    except (OSError, UnicodeError, ValueError) as exc:
        raise BoundedReviewEvidenceError(
            "Review evidence is unreadable"
        ) from exc


def _resolved_real_directory(path: Path) -> Path:
    require_real_directory(path)
    resolved = path.resolve(strict=True)
    if resolved != path.absolute():
        raise BoundedReviewEvidenceError(
            "Automatic review package directory is unsafe"
        )
    return resolved
