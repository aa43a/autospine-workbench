"""Strict read boundary for content-addressed split preview artifacts."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from .resolved_project import canonical_sha256
from .split_preview_contract import (
    SplitPreviewContractError,
    require_valid_split_preview,
)


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_ARTIFACT_BYTES = 2 * 1024 * 1024


class SplitPreviewReaderError(RuntimeError):
    """Raised when an immutable preview cannot be read or trusted."""


@dataclass(frozen=True, slots=True)
class LoadedSplitPreview:
    path: Path
    sha256: str
    document: dict[str, Any]


class SplitPreviewReader:
    """Load one exact preview without following aliases or symbolic links."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)
        self.root = self.state_root / "analysis"

    def load(self, project_id: str, digest: str) -> LoadedSplitPreview:
        if not isinstance(project_id, str) or not _SAFE_ID.fullmatch(project_id):
            raise SplitPreviewReaderError("Split preview identity is invalid")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise SplitPreviewReaderError("Split preview identity is invalid")
        path = self._resolve(project_id, digest)
        raw = self._read(path)
        document = _decode(raw)
        try:
            observed = canonical_sha256(document)
        except (TypeError, ValueError) as exc:
            raise SplitPreviewReaderError(
                "Split preview is not canonical JSON data"
            ) from exc
        if observed != digest:
            raise SplitPreviewReaderError(
                "Split preview does not match its content address"
            )
        if document.get("project_id") != project_id:
            raise SplitPreviewReaderError("Split preview belongs to another project")
        try:
            require_valid_split_preview(document)
        except SplitPreviewContractError as exc:
            raise SplitPreviewReaderError(f"Split preview is invalid: {exc}") from exc
        return LoadedSplitPreview(path=path, sha256=digest, document=document)

    def _resolve(self, project_id: str, digest: str) -> Path:
        project = self.root / project_id
        directory = project / "split-previews"
        lexical = directory / f"{digest}.json"
        chain = (self.state_root, self.root, project, directory, lexical)
        try:
            root = self.root.resolve(strict=True)
            resolved_directory = directory.resolve(strict=True)
            resolved = lexical.resolve(strict=True)
            resolved_directory.relative_to(root)
            resolved.relative_to(resolved_directory)
        except (OSError, RuntimeError, ValueError) as exc:
            raise SplitPreviewReaderError("Split preview was not found") from exc
        if any(item.is_symlink() for item in chain):
            raise SplitPreviewReaderError("Split preview path is unsafe")
        if not resolved_directory.is_dir() or not resolved.is_file():
            raise SplitPreviewReaderError("Split preview path is unsafe")
        return resolved

    @staticmethod
    def _read(path: Path) -> bytes:
        try:
            if path.stat().st_size > _MAX_ARTIFACT_BYTES:
                raise SplitPreviewReaderError("Split preview exceeds 2 MiB")
            raw = path.read_bytes()
        except SplitPreviewReaderError:
            raise
        except OSError as exc:
            raise SplitPreviewReaderError("Split preview cannot be read") from exc
        if len(raw) > _MAX_ARTIFACT_BYTES:
            raise SplitPreviewReaderError("Split preview exceeds 2 MiB")
        return raw


class _DuplicateKey(ValueError):
    pass


class _NonFiniteJson(ValueError):
    pass


def _decode(raw: bytes) -> dict[str, Any]:
    try:
        document = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except UnicodeDecodeError as exc:
        raise SplitPreviewReaderError("Split preview is not UTF-8") from exc
    except _DuplicateKey as exc:
        raise SplitPreviewReaderError(
            f"Split preview repeats a JSON key: {exc}"
        ) from exc
    except (_NonFiniteJson, json.JSONDecodeError) as exc:
        raise SplitPreviewReaderError("Split preview is not strict JSON") from exc
    if not isinstance(document, dict):
        raise SplitPreviewReaderError("Split preview root must be an object")
    return document


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise _NonFiniteJson(value)
