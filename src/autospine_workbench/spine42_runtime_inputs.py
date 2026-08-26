"""Read-once local inputs for the pinned Spine 4.2 runtime harness."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import stat
from typing import Any

from .png_rgba import RgbaPngError, decode_rgba_png
from .safe_input_files import SafeInputFileError, read_real_file, strict_json_object
from .spine42_contract import SPINE_RUNTIME_PACKAGE, SPINE_RUNTIME_VERSION
from .spine42_runtime_profile import (
    SPINE_PLAYER_JAVASCRIPT_SHA256,
    SPINE_PLAYER_STYLESHEET_SHA256,
)


class Spine42RuntimeInputError(ValueError):
    """Raised when an installed runtime or exported asset is unsafe."""


@dataclass(frozen=True, slots=True)
class Spine42RuntimePackage:
    root: Path
    javascript: Path
    stylesheet: Path
    license_file: Path
    javascript_bytes: bytes
    stylesheet_bytes: bytes
    javascript_sha256: str
    stylesheet_sha256: str


@dataclass(frozen=True, slots=True)
class Spine42ExportFiles:
    root: Path
    skeleton: Path
    atlas: Path
    texture: Path
    skeleton_sha256: str
    atlas_sha256: str
    texture_sha256: str
    texture_size: tuple[int, int]
    world_viewport: dict[str, float]
    skeleton_bytes: bytes
    atlas_bytes: bytes
    texture_bytes: bytes


def require_runtime_package(root: Path) -> Spine42RuntimePackage:
    """Verify an installed official package without copying or modifying it."""

    root = _real_directory(root, "runtime package root")
    package = _json_snapshot(root / "package.json", 64 * 1024, "runtime package.json")
    if package.get("name") != SPINE_RUNTIME_PACKAGE:
        raise Spine42RuntimeInputError("runtime package name is not pinned")
    if package.get("version") != SPINE_RUNTIME_VERSION:
        raise Spine42RuntimeInputError("runtime package version is not 4.2.119")
    dependencies = _mapping(package.get("dependencies"), "runtime dependencies")
    if dependencies.get("@esotericsoftware/spine-webgl") != SPINE_RUNTIME_VERSION:
        raise Spine42RuntimeInputError("spine-webgl dependency is not exact 4.2.119")
    javascript = root / "dist" / "iife" / "spine-player.min.js"
    stylesheet = root / "dist" / "spine-player.min.css"
    license_file = root / "LICENSE"
    javascript_bytes = _snapshot(javascript, 2 * 1024 * 1024, "runtime JavaScript")
    stylesheet_bytes = _snapshot(stylesheet, 512 * 1024, "runtime stylesheet")
    _snapshot(license_file, 256 * 1024, "runtime license")
    expected_js = _sha256(
        SPINE_PLAYER_JAVASCRIPT_SHA256, "runtime JavaScript SHA-256"
    )
    expected_css = _sha256(
        SPINE_PLAYER_STYLESHEET_SHA256, "runtime stylesheet SHA-256"
    )
    actual_js, actual_css = _sha(javascript_bytes), _sha(stylesheet_bytes)
    if actual_js != expected_js or actual_css != expected_css:
        raise Spine42RuntimeInputError(
            "runtime dist bytes differ from the pinned 4.2.119 snapshot"
        )
    return Spine42RuntimePackage(
        root, javascript, stylesheet, license_file,
        javascript_bytes, stylesheet_bytes, actual_js, actual_css,
    )


def require_export_files(root: Path) -> Spine42ExportFiles:
    """Load the fixed minimal export inventory from one explicit directory."""

    root = _real_directory(root, "Spine export directory")
    skeleton, atlas, texture = (
        root / "skeleton.json", root / "skeleton.atlas", root / "skeleton.png"
    )
    skeleton_bytes = _snapshot(skeleton, 16 * 1024 * 1024, "skeleton JSON")
    atlas_bytes = _snapshot(atlas, 1024 * 1024, "skeleton atlas")
    texture_bytes = _snapshot(texture, 64 * 1024 * 1024, "skeleton texture")
    document = _json_bytes(skeleton_bytes, "skeleton JSON")
    metadata = _mapping(document.get("skeleton"), "skeleton metadata")
    if metadata.get("spine") != "4.2":
        raise Spine42RuntimeInputError("skeleton JSON is not exact 4.2")
    world_viewport = _world_viewport(metadata)
    try:
        first = next(line.strip() for line in atlas_bytes.decode("utf-8").splitlines() if line.strip())
    except (UnicodeDecodeError, StopIteration) as exc:
        raise Spine42RuntimeInputError("skeleton atlas is empty or not UTF-8") from exc
    if first != "skeleton.png":
        raise Spine42RuntimeInputError("atlas first page must be skeleton.png")
    try:
        image = decode_rgba_png(texture_bytes, source_name="skeleton.png")
    except RgbaPngError as exc:
        raise Spine42RuntimeInputError(f"invalid skeleton texture: {exc}") from exc
    return Spine42ExportFiles(
        root, skeleton, atlas, texture,
        _sha(skeleton_bytes), _sha(atlas_bytes), _sha(texture_bytes),
        (image.width, image.height), world_viewport,
        skeleton_bytes, atlas_bytes, texture_bytes,
    )


def _json_snapshot(path: Path, limit: int, label: str) -> dict[str, Any]:
    return _json_bytes(_snapshot(path, limit, label), label)


def _json_bytes(raw: bytes, label: str) -> dict[str, Any]:
    try:
        return strict_json_object(raw, label)
    except SafeInputFileError as exc:
        raise Spine42RuntimeInputError(f"{label} is not strict JSON") from exc


def _real_directory(path: Path, label: str) -> Path:
    absolute = Path(os.path.abspath(os.fspath(Path(path))))
    try:
        candidates = (absolute, *absolute.parents)
        if any(_is_alias(item) or not stat.S_ISDIR(item.lstat().st_mode)
               for item in candidates):
            raise Spine42RuntimeInputError(f"{label} path contains an alias")
        resolved = absolute.resolve(strict=True)
    except Spine42RuntimeInputError:
        raise
    except (OSError, RuntimeError) as exc:
        raise Spine42RuntimeInputError(f"cannot inspect {label}") from exc
    try:
        same_directory = os.path.samefile(absolute, resolved)
    except OSError as exc:
        raise Spine42RuntimeInputError(f"cannot compare resolved {label}") from exc
    if not same_directory:
        raise Spine42RuntimeInputError(f"{label} path resolves through an alias")
    return absolute


def _snapshot(path: Path, limit: int, label: str) -> bytes:
    try:
        raw = read_real_file(path, limit, label)
    except SafeInputFileError as exc:
        raise Spine42RuntimeInputError(str(exc)) from exc
    if not raw:
        raise Spine42RuntimeInputError(f"{label} is empty")
    return raw


def _is_alias(path: Path) -> bool:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode):
        return True
    junction = getattr(path, "is_junction", None)
    if callable(junction) and junction():
        return True
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(metadata, "st_file_attributes", 0) & reparse)


def _world_viewport(metadata: Mapping[str, Any]) -> dict[str, float]:
    result = {key: metadata.get(key, 0) for key in ("x", "y", "width", "height")}
    for key, value in result.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            raise Spine42RuntimeInputError(f"skeleton {key} must be finite")
    if result["width"] <= 0 or result["height"] <= 0:
        raise Spine42RuntimeInputError("skeleton bounds must be positive")
    return {key: float(value) for key, value in result.items()}


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise Spine42RuntimeInputError(f"{label} must be an object")
    return value


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 \
            or any(character not in "0123456789abcdef" for character in value):
        raise Spine42RuntimeInputError(f"{label} is invalid")
    return value
