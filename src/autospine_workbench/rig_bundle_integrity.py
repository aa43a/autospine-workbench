"""Read-only, fail-closed verification of an on-disk RigIR bundle."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
from typing import Any

from .manifest_artifacts import (
    LayerManifestError,
    canonical_layer_artifact_path,
    normalized_path_key,
    require_safe_token,
)
from .png_rgba import (
    MAX_RGBA_BYTES,
    RgbaPngError,
    decode_rgba_png,
)
from .resolved_project import canonical_sha256
from .rig_bundle_validation import (
    MAX_RIG_JSON_BYTES,
    RigBundleError,
    bundle_address_sha256,
    read_json,
    required_sha,
    validate_bundle_documents,
)
from .rig_setup_artifact import (
    SETUP_DOCUMENT_NAME,
    SETUP_IMAGE_NAME,
    RigSetupArtifactError,
    verify_setup_artifact,
)


MAX_RIG_PNG_BYTES = MAX_RGBA_BYTES + 1024 * 1024
_DOCUMENT_NAMES = (
    "rig.json",
    "run-manifest.json",
    "probes.json",
    SETUP_DOCUMENT_NAME,
)


@dataclass(frozen=True, slots=True)
class VerifiedRigBundle:
    directory: Path
    project_id: str
    rig: dict[str, Any]
    run: dict[str, Any]
    probes: dict[str, Any]
    setup: dict[str, Any]
    setup_png: bytes
    rig_sha256: str
    run_sha256: str
    probe_sha256: str
    setup_sha256: str
    bundle_sha256: str
    region_sha256: dict[str, str]
    _region_png_items: tuple[tuple[str, bytes], ...] = field(
        default=(), repr=False
    )

    @property
    def region_pngs(self) -> dict[str, bytes]:
        """Return a copy of path-bound PNG bytes captured during verification."""

        return dict(self._region_png_items)


def verify_rig_bundle_directory(
    path: Path,
    *,
    require_content_address: bool = True,
    expected_project_id: str | None = None,
) -> VerifiedRigBundle:
    """Read and fully validate one immutable region-only RigIR bundle."""

    directory = _safe_directory(Path(path), "RigIR bundle")
    documents = {
        name: read_json(
            _exact_child(directory, name), max_bytes=MAX_RIG_JSON_BYTES
        )
        for name in _DOCUMENT_NAMES
    }
    rig = documents["rig.json"]
    run = documents["run-manifest.json"]
    probes = documents["probes.json"]
    setup = documents[SETUP_DOCUMENT_NAME]
    try:
        project_id = require_safe_token(run.get("project_id"), "Project id")
    except LayerManifestError as exc:
        raise RigBundleError("RigIR bundle project id is unsafe") from exc
    if expected_project_id is not None and project_id != expected_project_id:
        raise RigBundleError("RigIR bundle belongs to another project")
    rig_sha, run_sha, probe_sha, _layer_sha = validate_bundle_documents(
        project_id, rig, run, probes
    )
    setup_sha = canonical_sha256(setup)
    bundle_sha = bundle_address_sha256(rig_sha, run_sha, probe_sha, setup_sha)
    regions = _region_inventory(rig)
    expected_files = set(_DOCUMENT_NAMES) | {SETUP_IMAGE_NAME} | set(regions)
    expected_directories = _parent_directories(regions)
    _verify_inventory(directory, expected_files, expected_directories)
    region_pngs = _verify_regions(directory, regions)
    setup_png = _read_limited(
        _exact_child(directory, SETUP_IMAGE_NAME), MAX_RIG_PNG_BYTES, "Setup PNG"
    )
    try:
        verify_setup_artifact(
            setup,
            setup_png,
            project_id=project_id,
            rig=rig,
            rig_sha256=rig_sha,
            bundle_path=directory,
        )
    except RigSetupArtifactError as exc:
        raise RigBundleError("Canonical setup artifact is invalid") from exc
    if require_content_address:
        _verify_content_address(directory, project_id, rig_sha, bundle_sha)
    return VerifiedRigBundle(
        directory=directory,
        project_id=project_id,
        rig=rig,
        run=run,
        probes=probes,
        setup=setup,
        setup_png=setup_png,
        rig_sha256=rig_sha,
        run_sha256=run_sha,
        probe_sha256=probe_sha,
        setup_sha256=setup_sha,
        bundle_sha256=bundle_sha,
        region_sha256=regions,
        _region_png_items=tuple(sorted(region_pngs.items())),
    )


def _region_inventory(rig: dict[str, Any]) -> dict[str, str]:
    attachments = rig.get("attachments")
    if not isinstance(attachments, list):
        raise RigBundleError("RigIR attachments must be an array")
    regions: dict[str, str] = {}
    portable_paths: set[str] = set()
    for attachment in attachments:
        if not isinstance(attachment, dict) or attachment.get("type") != "region":
            raise RigBundleError("RigIR bundle contains a non-region attachment")
        source_ids = attachment.get("source_layer_ids")
        if not isinstance(source_ids, list) or len(source_ids) != 1:
            raise RigBundleError("Region attachment source identity is invalid")
        try:
            layer_id = require_safe_token(source_ids[0], "Source layer id")
            relative = canonical_layer_artifact_path(layer_id)
        except LayerManifestError as exc:
            raise RigBundleError("Region attachment path is not canonical") from exc
        if attachment.get("image_path") != relative:
            raise RigBundleError("Region attachment path is not canonical")
        key = normalized_path_key(relative)
        if key in portable_paths:
            raise RigBundleError("Region attachment path is duplicated")
        portable_paths.add(key)
        regions[relative] = required_sha(
            attachment.get("image_sha256"), f"region {layer_id} image"
        )
    return dict(sorted(regions.items()))


def _verify_regions(directory: Path, regions: dict[str, str]) -> dict[str, bytes]:
    snapshots: dict[str, bytes] = {}
    for relative, expected_sha in regions.items():
        path = _relative_file(directory, relative)
        raw = _read_limited(path, MAX_RIG_PNG_BYTES, f"Region {relative}")
        if hashlib.sha256(raw).hexdigest() != expected_sha:
            raise RigBundleError(f"Region image hash mismatch: {relative}")
        try:
            decode_rgba_png(raw, source_name=relative)
        except RgbaPngError as exc:
            raise RigBundleError(f"Region image profile is invalid: {relative}") from exc
        snapshots[relative] = raw
    return snapshots


def _verify_inventory(
    directory: Path, expected_files: set[str], expected_directories: set[str]
) -> None:
    files: set[str] = set()
    directories: set[str] = set()
    pending = [(directory, PurePosixPath())]
    while pending:
        parent, prefix = pending.pop()
        try:
            children = list(parent.iterdir())
        except OSError as exc:
            raise RigBundleError("RigIR bundle inventory cannot be read") from exc
        for child in children:
            if _is_alias(child):
                raise RigBundleError("RigIR bundle contains a path alias")
            relative = prefix / child.name
            value = relative.as_posix()
            if child.is_file():
                files.add(value)
            elif child.is_dir():
                directories.add(value)
                pending.append((child, relative))
            else:
                raise RigBundleError("RigIR bundle contains an unsupported entry")
    if files != expected_files or directories != expected_directories:
        raise RigBundleError("RigIR bundle has missing or unexpected entries")


def _parent_directories(paths: dict[str, str]) -> set[str]:
    result: set[str] = set()
    for relative in paths:
        parent = PurePosixPath(relative).parent
        while parent.as_posix() != ".":
            result.add(parent.as_posix())
            parent = parent.parent
    return result


def _verify_content_address(
    directory: Path, project_id: str, rig_sha: str, bundle_sha: str
) -> None:
    if (
        directory.name != bundle_sha
        or directory.parent.name != rig_sha
        or directory.parent.parent.name != "rig-ir"
        or directory.parent.parent.parent.name != project_id
    ):
        raise RigBundleError("RigIR bundle content-address path is invalid")


def _relative_file(root: Path, relative: str) -> Path:
    current = root
    for part in PurePosixPath(relative).parts:
        current = _exact_child(current, part)
    return current


def _exact_child(parent: Path, name: str) -> Path:
    try:
        matches = [item for item in parent.iterdir() if item.name.casefold() == name.casefold()]
    except OSError as exc:
        raise RigBundleError("RigIR bundle path cannot be enumerated") from exc
    if len(matches) != 1 or matches[0].name != name or _is_alias(matches[0]):
        raise RigBundleError(f"RigIR bundle path is missing or aliased: {name}")
    return matches[0]


def _safe_directory(path: Path, label: str) -> Path:
    if _is_alias(path) or not path.is_dir():
        raise RigBundleError(f"{label} is not a real directory")
    try:
        return path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise RigBundleError(f"{label} cannot be resolved") from exc


def _read_limited(path: Path, maximum: int, label: str) -> bytes:
    try:
        before = path.lstat()
        if _is_alias(path) or not stat.S_ISREG(before.st_mode):
            raise RigBundleError(f"{label} is not a regular file")
        if before.st_size > maximum:
            raise RigBundleError(f"{label} exceeds its byte limit")
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            value = handle.read(maximum + 1)
            finished = os.fstat(handle.fileno())
        after = path.lstat()
    except RigBundleError:
        raise
    except OSError as exc:
        raise RigBundleError(f"{label} cannot be read") from exc
    if len(value) > maximum:
        raise RigBundleError(f"{label} exceeds its byte limit")
    if (
        len(value) != before.st_size
        or _file_identity(before) != _file_identity(opened)
        or _file_identity(opened) != _file_identity(finished)
        or _file_identity(finished) != _file_identity(after)
    ):
        raise RigBundleError(f"{label} changed while being read")
    return value


def _file_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        getattr(value, "st_dev", 0),
        getattr(value, "st_ino", 0),
    )


def _is_alias(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return True
    if stat.S_ISLNK(info.st_mode):
        return True
    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction):
        try:
            if is_junction():
                return True
        except OSError:
            return True
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(info, "st_file_attributes", 0) & reparse)
