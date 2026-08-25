"""Strict read boundary for content-addressed split preview artifacts."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import stat
from typing import Any

from .manifest_artifacts import (
    LayerManifestError,
    require_safe_token,
    require_sha256,
)
from .resolved_project import canonical_sha256
from .split_preview_contract import (
    SplitPreviewContractError,
    require_valid_split_preview,
)


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
        try:
            project_id = require_safe_token(project_id, "Project id")
            digest = require_sha256(digest, "Split preview digest")
        except LayerManifestError as exc:
            raise SplitPreviewReaderError("Split preview identity is invalid") from exc
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
        try:
            if _is_path_alias(self.state_root):
                raise SplitPreviewReaderError("Split preview path is unsafe")
            state_root = self.state_root.resolve(strict=True)
            root = _exact_child(state_root, "analysis", want_directory=True)
            project = _exact_child(root, project_id, want_directory=True)
            directory = _exact_child(project, "split-previews", want_directory=True)
            lexical = _exact_child(directory, f"{digest}.json", want_directory=False)
            resolved_root = root.resolve(strict=True)
            resolved_directory = directory.resolve(strict=True)
            resolved = lexical.resolve(strict=True)
            resolved_root.relative_to(state_root)
            resolved_directory.relative_to(resolved_root)
            resolved.relative_to(resolved_directory)
        except SplitPreviewReaderError:
            raise
        except (OSError, RuntimeError, ValueError) as exc:
            raise SplitPreviewReaderError("Split preview was not found") from exc
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


def _exact_child(parent: Path, name: str, *, want_directory: bool) -> Path:
    """Resolve one exact portable component without following path aliases."""

    if _is_path_alias(parent):
        raise SplitPreviewReaderError("Split preview path is unsafe")
    try:
        matches = [
            child for child in parent.iterdir() if child.name.casefold() == name.casefold()
        ]
    except OSError as exc:
        raise SplitPreviewReaderError("Split preview was not found") from exc
    if not matches:
        raise SplitPreviewReaderError("Split preview was not found")
    if len(matches) != 1 or matches[0].name != name or _is_path_alias(matches[0]):
        raise SplitPreviewReaderError("Split preview path is unsafe")
    child = matches[0]
    if (want_directory and not child.is_dir()) or (
        not want_directory and not child.is_file()
    ):
        raise SplitPreviewReaderError("Split preview path is unsafe")
    return child


def _is_path_alias(path: Path) -> bool:
    """Reject symlinks and every junction/reparse marker exposed by Python."""

    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            return True
        is_junction = getattr(path, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        attributes = getattr(metadata, "st_file_attributes", 0)
        return bool(reparse and attributes & reparse)
    except OSError:
        return False


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
