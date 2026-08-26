"""Fail-closed identity snapshots for the browser used by P10 captures."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import threading
from typing import Any


FORMAT = "autospine-browser-executable-snapshot"
VERSION = 1
MAX_EXECUTABLE_BYTES = 512 * 1024 * 1024
MAX_VERSION_OUTPUT_BYTES = 4 * 1024
VERSION_TIMEOUT_SECONDS = 5.0
KILL_GRACE_SECONDS = 1.0
_CHUNK_BYTES = 1024 * 1024
_VERSION_PATTERNS = (
    ("google-chrome", re.compile(
        r"Google Chrome(?: for Testing)? "
        r"(?P<version>[0-9]{1,6}(?:\.[0-9]{1,6}){3})"
    )),
    ("chromium", re.compile(
        r"Chromium (?P<version>[0-9]{1,6}(?:\.[0-9]{1,6}){3})"
        r"(?: built on [^\r\n]{1,160})?"
    )),
)


class BrowserExecutableSnapshotError(ValueError):
    """Raised when a browser executable cannot be identified safely."""


@dataclass(frozen=True, slots=True)
class BrowserExecutableSnapshot:
    """Exact launcher identity used for one bounded capture run."""

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
    output = _bounded_version_output(executable)
    final_sha256, final_size = _hash_executable(executable)
    if (final_sha256, final_size) != (executable_sha256, size):
        raise BrowserExecutableSnapshotError(
            "browser executable changed while its version was queried"
        )
    family, reported_version = _parse_version_output(output)
    return BrowserExecutableSnapshot(
        path=os.fspath(executable),
        family=family,
        reported_version=reported_version,
        version_output_sha256=hashlib.sha256(output).hexdigest(),
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
        if before.st_size <= 0 or before.st_size > MAX_EXECUTABLE_BYTES:
            raise BrowserExecutableSnapshotError(
                "browser executable size is outside the allowed range"
            )
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or not _same_file(before, opened):
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
            or not _same_snapshot(before, opened)
            or not _same_snapshot(opened, after)
            or not _same_snapshot(after, final)
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
            os.close(descriptor)


def _bounded_version_output(path: Path) -> bytes:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        process = subprocess.Popen(
            [os.fspath(path), "--version"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=False,
            cwd=os.fspath(path.parent),
            close_fds=True,
            creationflags=creationflags,
        )
    except OSError as exc:
        raise BrowserExecutableSnapshotError(
            "browser version command could not be started"
        ) from exc
    if process.stdout is None:  # pragma: no cover - guaranteed by PIPE
        process.kill()
        raise BrowserExecutableSnapshotError("browser version output is unavailable")
    output, overflow, read_failed = bytearray(), threading.Event(), threading.Event()

    def read_output() -> None:
        try:
            while chunk := process.stdout.read(1024):
                remaining = MAX_VERSION_OUTPUT_BYTES + 1 - len(output)
                if remaining > 0:
                    output.extend(chunk[:remaining])
                if len(output) > MAX_VERSION_OUTPUT_BYTES or len(chunk) > remaining:
                    overflow.set()
                    process.kill()
        except (OSError, ValueError):
            read_failed.set()

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    timed_out = False
    try:
        return_code = process.wait(timeout=VERSION_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        try:
            return_code = process.wait(timeout=KILL_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            return_code = None
    reader.join(KILL_GRACE_SECONDS)
    if reader.is_alive():
        process.stdout.close()
        reader.join(KILL_GRACE_SECONDS)
    elif not process.stdout.closed:
        process.stdout.close()
    if timed_out:
        raise BrowserExecutableSnapshotError("browser version command timed out")
    if reader.is_alive() or read_failed.is_set():
        raise BrowserExecutableSnapshotError("browser version output could not be read")
    if overflow.is_set():
        raise BrowserExecutableSnapshotError("browser version output exceeds its limit")
    if return_code != 0:
        raise BrowserExecutableSnapshotError("browser version command failed")
    return bytes(output)


def _parse_version_output(output: bytes) -> tuple[str, str]:
    try:
        text = output.decode("utf-8").strip()
    except UnicodeError as exc:
        raise BrowserExecutableSnapshotError(
            "browser version output is not valid UTF-8"
        ) from exc
    for family, pattern in _VERSION_PATTERNS:
        match = pattern.fullmatch(text)
        if match is not None:
            return family, match.group("version")
    raise BrowserExecutableSnapshotError(
        "browser must report itself as Google Chrome or Chromium"
    )


def _is_alias(path: Path, metadata: os.stat_result) -> bool:
    junction = getattr(path, "is_junction", None)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(metadata.st_mode) or (
        callable(junction) and junction()
    ) or bool(getattr(metadata, "st_file_attributes", 0) & reparse)


def _same_file(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _same_snapshot(left: os.stat_result, right: os.stat_result) -> bool:
    return _same_file(left, right) and (
        left.st_size, left.st_mtime_ns, left.st_ctime_ns
    ) == (right.st_size, right.st_mtime_ns, right.st_ctime_ns)
