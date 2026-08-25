"""Read-once, bounded input files and strict JSON snapshots."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
from typing import Any


class SafeInputFileError(ValueError):
    """Raised when an explicit command input is aliased, racy, or malformed."""


def read_real_file(path: Path, maximum: int, label: str) -> bytes:
    """Read one regular non-aliased file once under a fixed byte ceiling."""

    try:
        absolute = Path(os.path.abspath(os.fspath(Path(path))))
        before = absolute.lstat()
        if _is_alias(absolute, before) or not stat.S_ISREG(before.st_mode):
            raise SafeInputFileError(f"{label} is not a real regular file")
        _require_real_parents(absolute, label)
        if before.st_size > maximum:
            raise SafeInputFileError(f"{label} exceeds its byte limit")
        with absolute.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if not _same_file(before, opened) or not stat.S_ISREG(opened.st_mode):
                raise SafeInputFileError(f"{label} changed before it was read")
            data = handle.read(maximum + 1)
            after = os.fstat(handle.fileno())
        if (
            len(data) > maximum
            or len(data) != before.st_size
            or not _same_snapshot(opened, after)
        ):
            raise SafeInputFileError(f"{label} changed while it was read")
        return data
    except SafeInputFileError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise SafeInputFileError(f"{label} cannot be safely read") from exc


def strict_json_object(data: bytes, label: str) -> dict[str, Any]:
    """Decode UTF-8 JSON while rejecting duplicate keys and non-finite numbers."""

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise SafeInputFileError(
                    f"{label} contains a duplicate JSON key"
                )
            result[key] = value
        return result

    def nonfinite(_value):
        raise SafeInputFileError(f"{label} contains a non-finite number")

    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=nonfinite,
        )
    except SafeInputFileError:
        raise
    except (
        UnicodeError, json.JSONDecodeError, RecursionError, TypeError, ValueError,
    ) as exc:
        raise SafeInputFileError(f"{label} is not valid UTF-8 JSON") from exc
    if type(value) is not dict:
        raise SafeInputFileError(f"{label} must be a JSON object")
    return value


def _is_alias(path: Path, metadata: os.stat_result) -> bool:
    if stat.S_ISLNK(metadata.st_mode):
        return True
    junction = getattr(path, "is_junction", None)
    if callable(junction) and junction():
        return True
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(metadata, "st_file_attributes", 0) & reparse)


def _require_real_parents(path: Path, label: str) -> None:
    for parent in path.parents:
        metadata = parent.lstat()
        if _is_alias(parent, metadata) or not stat.S_ISDIR(metadata.st_mode):
            raise SafeInputFileError(f"{label} path contains an alias")


def _same_file(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _same_snapshot(left: os.stat_result, right: os.stat_result) -> bool:
    return _same_file(left, right) and (
        left.st_size, left.st_mtime_ns
    ) == (right.st_size, right.st_mtime_ns)
