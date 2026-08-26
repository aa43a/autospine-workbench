"""Fail-closed identity snapshots for the browser used by P10 captures."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat
import sys
from typing import Any

from .browser_version_identity import (
    BrowserVersionIdentityError,
    VERSION_IDENTITY_HASH_SEMANTICS,
    browser_version_identity_sha256,
    identify_browser_version,
)

FORMAT, VERSION = "autospine-browser-executable-snapshot", 1
MAX_EXECUTABLE_BYTES = 512 * 1024 * 1024
VERSION_OUTPUT_SHA256_SEMANTICS = VERSION_IDENTITY_HASH_SEMANTICS
_CHUNK_BYTES = 1024 * 1024


class BrowserExecutableSnapshotError(ValueError):
    """Raised when a browser executable cannot be identified safely."""


@dataclass(frozen=True, slots=True)
class BrowserExecutableSnapshot:
    """Exact launcher identity used for one bounded capture run.

    ``version_output_sha256`` follows ``VERSION_OUTPUT_SHA256_SEMANTICS``.
    """

    path: str
    family: str
    reported_version: str
    version_output_sha256: str
    executable_sha256: str
    size_bytes: int

    def to_document(self) -> dict[str, Any]:
        return {
            "format": FORMAT,
            "version": VERSION,
            "path": self.path,
            "family": self.family,
            "reported_version": self.reported_version,
            "version_output_sha256": self.version_output_sha256,
            "executable_sha256": self.executable_sha256,
            "size_bytes": self.size_bytes,
        }


def snapshot_browser_executable(path: str | Path) -> BrowserExecutableSnapshot:
    """Hash and identify one explicit Chrome/Chromium executable."""

    executable = _explicit_real_executable(path)
    executable_sha256, size = _hash_executable(executable)
    try:
        identity = identify_browser_version(executable)
    except BrowserVersionIdentityError as exc:
        raise BrowserExecutableSnapshotError(
            "browser version identity cannot be established"
        ) from exc
    final_sha256, final_size = _hash_executable(executable)
    if (final_sha256, final_size) != (executable_sha256, size):
        raise BrowserExecutableSnapshotError(
            "browser executable changed while its version was queried"
        )
    return BrowserExecutableSnapshot(
        path=os.fspath(executable),
        family=identity.family,
        reported_version=identity.reported_version,
        version_output_sha256=browser_version_identity_sha256(
            identity.family, identity.reported_version
        ),
        executable_sha256=executable_sha256,
        size_bytes=size,
    )


def recheck_browser_executable(
    expected: BrowserExecutableSnapshot,
) -> BrowserExecutableSnapshot:
    """Re-snapshot the launcher and require every recorded field to match."""

    if type(expected) is not BrowserExecutableSnapshot:
        raise BrowserExecutableSnapshotError("expected browser snapshot is invalid")
    current = snapshot_browser_executable(expected.path)
    if current != expected:
        raise BrowserExecutableSnapshotError(
            "browser executable changed after its identity snapshot"
        )
    return current


def _explicit_real_executable(path: str | Path) -> Path:
    try:
        lexical = Path(path)
        if not lexical.is_absolute():
            raise BrowserExecutableSnapshotError(
                "browser executable path must be explicit and absolute"
            )
        absolute = Path(os.path.abspath(os.fspath(lexical)))
        if lexical != absolute:
            raise BrowserExecutableSnapshotError(
                "browser executable path must not contain lexical aliases"
            )
        metadata = absolute.lstat()
        if _is_alias(absolute, metadata) or not stat.S_ISREG(metadata.st_mode):
            raise BrowserExecutableSnapshotError(
                "browser executable must be a real regular file"
            )
        for parent in absolute.parents:
            parent_metadata = parent.lstat()
            if _is_alias(parent, parent_metadata) or not stat.S_ISDIR(
                parent_metadata.st_mode
            ):
                raise BrowserExecutableSnapshotError(
                    "browser executable path contains an aliased parent"
                )
        if not os.access(absolute, os.X_OK):
            raise BrowserExecutableSnapshotError(
                "browser executable is not executable by this process"
            )
        if absolute.resolve(strict=True) != absolute:
            raise BrowserExecutableSnapshotError(
                "browser executable path resolves through an alias"
            )
        return absolute
    except BrowserExecutableSnapshotError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise BrowserExecutableSnapshotError(
            "browser executable path cannot be safely inspected"
        ) from exc


def _hash_executable(path: Path) -> tuple[str, int]:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        before = path.lstat()
        if _is_alias(path, before) or not stat.S_ISREG(before.st_mode):
            raise BrowserExecutableSnapshotError("browser executable became aliased")
        if not 0 < before.st_size <= MAX_EXECUTABLE_BYTES:
            raise BrowserExecutableSnapshotError(
                "browser executable size is outside the allowed range"
            )
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or not _same_content_state(
            before, opened
        ):
            raise BrowserExecutableSnapshotError(
                "browser executable changed before hashing"
            )
        digest, total = hashlib.sha256(), 0
        while True:
            chunk = os.read(descriptor, min(_CHUNK_BYTES, before.st_size - total + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_EXECUTABLE_BYTES or total > before.st_size:
                raise BrowserExecutableSnapshotError(
                    "browser executable changed while hashing"
                )
            digest.update(chunk)
        after = os.fstat(descriptor)
        final = path.lstat()
        if (
            total != before.st_size
            or not _same_path_snapshot(before, final)
            or not _same_handle_snapshot(opened, after)
            or not _same_content_state(before, opened)
            or not _same_content_state(after, final)
            or _is_alias(path, final)
        ):
            raise BrowserExecutableSnapshotError(
                "browser executable changed while hashing"
            )
        return digest.hexdigest(), total
    except BrowserExecutableSnapshotError:
        raise
    except OSError as exc:
        raise BrowserExecutableSnapshotError(
            "browser executable cannot be hashed safely"
        ) from exc
    finally:
        if descriptor >= 0:
            primary_error = sys.exc_info()[1]
            try:
                os.close(descriptor)
            except OSError as exc:
                if primary_error is not None:
                    primary_error.add_note(
                        f"Browser executable descriptor cleanup also failed: {exc}"
                    )
                else:
                    raise BrowserExecutableSnapshotError(
                        "browser executable descriptor could not be closed"
                    ) from exc


def _is_alias(path: Path, metadata: os.stat_result) -> bool:
    junction = getattr(path, "is_junction", None)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(metadata.st_mode) or (
        callable(junction) and junction()
    ) or bool(getattr(metadata, "st_file_attributes", 0) & reparse)


def _same_content_state(left: os.stat_result, right: os.stat_result) -> bool:
    """Compare fields meaningful across a Windows path and open handle."""
    left_state = (left.st_dev, left.st_ino, left.st_size, left.st_mtime_ns)
    right_state = (right.st_dev, right.st_ino, right.st_size, right.st_mtime_ns)
    return left_state == right_state


def _same_path_snapshot(left: os.stat_result, right: os.stat_result) -> bool:
    return _same_content_state(left, right) and left.st_ctime_ns == right.st_ctime_ns


def _same_handle_snapshot(left: os.stat_result, right: os.stat_result) -> bool:
    return _same_content_state(left, right) and left.st_ctime_ns == right.st_ctime_ns
