"""Filesystem boundary for append-only override documents."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping


_HISTORY_NAME = re.compile(r"^r([0-9]{6,})\.json$")
_MAX_BYTES = 2 * 1024 * 1024


class OverrideFileError(RuntimeError):
    """Raised when override files cannot be read or published safely."""


class OverrideFiles:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def document_paths(self, project_id: str) -> list[tuple[Path, int | None]]:
        project_dir = self.root / project_id
        paths: list[tuple[Path, int | None]] = []
        legacy = self.root / f"{project_id}.json"
        latest = project_dir / "latest.json"
        if legacy.is_file():
            paths.append((legacy, None))
        if latest.is_file():
            paths.append((latest, None))
        history = project_dir / "history"
        if not history.is_dir():
            return paths
        try:
            entries = sorted(history.iterdir(), key=lambda item: item.name)
        except OSError as exc:
            raise OverrideFileError("Could not enumerate override history") from exc
        for path in entries:
            match = _HISTORY_NAME.fullmatch(path.name)
            if match and path.is_file():
                paths.append((path, int(match.group(1))))
        return paths

    @staticmethod
    def read(path: Path) -> Mapping[str, Any]:
        try:
            if path.stat().st_size > _MAX_BYTES:
                raise OverrideFileError(f"Override document is too large: {path.name}")
            with path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle, object_pairs_hook=_unique_object)
        except OverrideFileError:
            raise
        except _DuplicateJsonKey as exc:
            raise OverrideFileError(
                f"Override document contains duplicate field {exc}: {path.name}"
            ) from exc
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise OverrideFileError(f"Cannot read override document: {path.name}") from exc
        if not isinstance(raw, Mapping):
            raise OverrideFileError("Override document must be a JSON object")
        return raw

    @staticmethod
    def publish(history_dir: Path, document: Mapping[str, Any]) -> None:
        destination = history_dir / _history_filename(int(document["revision"]))
        encoded = _encode(document)
        temp_path: Path | None = None
        try:
            fd, raw_temp = tempfile.mkstemp(
                prefix=f".{destination.stem}.", suffix=".tmp", dir=history_dir
            )
            temp_path = Path(raw_temp)
            with os.fdopen(fd, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.link(temp_path, destination)
        except FileExistsError:
            raise
        except OSError as exc:
            raise OverrideFileError("Could not append override history") from exc
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    @staticmethod
    def write_latest(destination: Path, document: Mapping[str, Any]) -> None:
        encoded = _encode(document)
        temp_path: Path | None = None
        try:
            fd, raw_temp = tempfile.mkstemp(
                prefix=".latest.", suffix=".tmp", dir=destination.parent
            )
            temp_path = Path(raw_temp)
            with os.fdopen(fd, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, destination)
            temp_path = None
        except OSError as exc:
            raise OverrideFileError("Could not atomically save overrides") from exc
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass


def history_filename(revision: int) -> str:
    return _history_filename(revision)


def _history_filename(revision: int) -> str:
    return f"r{revision:06d}.json"


def _encode(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


class _DuplicateJsonKey(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result
