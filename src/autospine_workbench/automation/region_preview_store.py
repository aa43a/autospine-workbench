"""Content addressed preview files, isolated from certified Spine bundles."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

from ..manifest_artifacts import require_safe_token, require_sha256
from ..resolved_project import canonical_sha256


FILES = frozenset({"skeleton.json", "skeleton.atlas", "skeleton.png", "source.json", "qa.json"})
LIMITS = {"skeleton.json": 32 << 20, "skeleton.atlas": 4 << 20,
          "skeleton.png": 72 << 20, "source.json": 16384, "qa.json": 16384}
SOURCE_KEYS = frozenset({"layer_manifest_sha256", "rig_sha256", "rig_bundle_sha256"})


class RegionPreviewError(ValueError):
    """An exact preview could not be safely built or verified."""


@dataclass(frozen=True)
class RegionPreviewBundle:
    path: Path
    _items: tuple[tuple[str, bytes], ...]
    _addresses_json: str

    @property
    def files(self) -> dict[str, bytes]:
        return dict(self._items)

    @property
    def addresses(self) -> dict[str, Any]:
        return json.loads(self._addresses_json)


def require_sources(value: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != SOURCE_KEYS:
        raise RegionPreviewError("Preview requires an exact P2 source triple")
    return {key: require_sha256(value[key], key) for key in sorted(SOURCE_KEYS)}


def safe_path(path: Path) -> None:
    """Reject symlinks, junctions, and aliases on all existing ancestors."""
    for item in (path, *path.parents):
        if item.is_symlink() or getattr(item, "is_junction", lambda: False)():
            raise RegionPreviewError("Preview path contains a filesystem alias")


def preview_path(state_root: Path, project_id: str, digest: str) -> Path:
    require_safe_token(project_id, "Project id")
    require_sha256(digest, "Preview bundle")
    path = Path(state_root) / "builds" / project_id / "region-previews" / digest
    safe_path(path)
    return path


def _digest(files: Mapping[str, bytes]) -> str:
    if set(files) != FILES or any(type(value) is not bytes for value in files.values()):
        raise RegionPreviewError("Preview inventory is invalid")
    return canonical_sha256({
        "schema": "autospine.region-preview-bundle/v1",
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
    })


def publish_preview(state_root: Path, project_id: str, files: Mapping[str, bytes]) -> str:
    digest = _digest(files)
    target = preview_path(state_root, project_id, digest)
    target.parent.mkdir(parents=True, exist_ok=True)
    safe_path(target)
    if target.exists():
        if read_preview(state_root, project_id, digest).files != dict(files):
            raise RegionPreviewError("Existing preview does not match compilation")
        return digest
    with tempfile.TemporaryDirectory(prefix=".region-preview-", dir=target.parent) as temporary:
        staging = Path(temporary) / "bundle"
        staging.mkdir()
        for name, data in files.items():
            if len(data) > LIMITS[name]:
                raise RegionPreviewError("Preview file exceeds size limit")
            (staging / name).write_bytes(data)
        try:
            staging.rename(target)
        except OSError:
            if not target.exists():
                raise
            if read_preview(state_root, project_id, digest).files != dict(files):
                raise RegionPreviewError("Concurrent preview publication differs")
    return digest


def read_preview(state_root: Path, project_id: str, digest: str) -> RegionPreviewBundle:
    path = preview_path(state_root, project_id, digest)
    if not path.is_dir() or {item.name for item in path.iterdir()} != FILES:
        raise RegionPreviewError("Preview directory inventory differs")
    files: dict[str, bytes] = {}
    for name in sorted(FILES):
        item = path / name
        safe_path(item)
        if not item.is_file() or item.stat().st_nlink != 1:
            raise RegionPreviewError("Preview file is not a regular independent file")
        with item.open("rb") as handle:
            before = os.fstat(handle.fileno())
            data = handle.read(LIMITS[name] + 1)
            after = os.fstat(handle.fileno())
        if len(data) > LIMITS[name] or (before.st_size, before.st_mtime_ns) != (
            after.st_size, after.st_mtime_ns
        ):
            raise RegionPreviewError("Preview file changed or exceeds size limit")
        files[name] = data
    if _digest(files) != digest:
        raise RegionPreviewError("Preview content does not match its address")
    source = json.loads(files["source.json"])
    if source.get("schema") != "autospine.region-preview-source/v1" \
            or source.get("project_id") != project_id or source.get("authority") != "none":
        raise RegionPreviewError("Preview source identity is invalid")
    sources = require_sources(source.get("source_addresses"))
    addresses = {"bundle_sha256": digest, "source_addresses": sources}
    for key, name in (("skeleton_json", "skeleton.json"), ("atlas", "skeleton.atlas"),
                      ("png", "skeleton.png"), ("qa", "qa.json")):
        addresses[f"{key}_sha256"] = hashlib.sha256(files[name]).hexdigest()
    return RegionPreviewBundle(path, tuple(sorted(files.items())), json.dumps(addresses))
