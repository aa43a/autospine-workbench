"""Create same-parent staging directories without changing Windows ACL scope."""

from __future__ import annotations

import os
from pathlib import Path
import secrets
import stat
import tempfile


_MAX_WINDOWS_ATTEMPTS = 128
_WINDOWS = os.name == "nt"


def create_same_parent_staging(parent: Path, *, prefix: str) -> Path:
    """Atomically create one unpredictable staging child of ``parent``.

    POSIX keeps ``tempfile.mkdtemp`` and its owner-only mode.  On modern
    Windows, ``mkdtemp`` requests mode ``0o700``; Python translates that into
    a protected DACL which survives a later directory rename.  Creating the
    directory with the normal Windows mode instead preserves parent ACL
    inheritance for the final content-addressed directory.
    """

    root = _require_real_directory(Path(parent), "staging parent")
    _require_prefix(prefix)
    if not _WINDOWS:
        return Path(tempfile.mkdtemp(prefix=prefix, dir=root))
    for _attempt in range(_MAX_WINDOWS_ATTEMPTS):
        candidate = root / f"{prefix}{secrets.token_hex(16)}"
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        try:
            return _require_real_directory(candidate, "staging directory")
        except OSError:
            try:
                candidate.rmdir()
            except OSError:
                pass
            raise
    raise FileExistsError("could not allocate a unique staging directory")


def _require_prefix(prefix: str) -> None:
    if not isinstance(prefix, str) or not prefix \
            or Path(prefix).name != prefix \
            or any(character in prefix for character in "/\\\x00"):
        raise ValueError("staging prefix must be one non-empty path component")


def _require_real_directory(path: Path, label: str) -> Path:
    try:
        info = path.lstat()
        junction = getattr(path, "is_junction", None)
        is_junction = callable(junction) and junction()
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if stat.S_ISLNK(info.st_mode) or is_junction \
                or bool(getattr(info, "st_file_attributes", 0) & reparse) \
                or not stat.S_ISDIR(info.st_mode):
            raise OSError(f"{label} is not a real directory")
        return path
    except OSError:
        raise
    except (RuntimeError, TypeError, ValueError) as exc:
        raise OSError(f"{label} cannot be inspected") from exc


__all__ = ["create_same_parent_staging"]
