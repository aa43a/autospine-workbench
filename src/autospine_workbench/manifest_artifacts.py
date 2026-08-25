"""Fail-closed identity, path, and raster checks for Layer Manifest assets."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import struct
from typing import Any, Mapping

from .split_bundle_validation import SplitBundleValidationError, validate_split_bundle
from .split_derivation_contract import SplitDerivationError, normalize_derivation


_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_MANIFEST_BYTES = 4 * 1024 * 1024
_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)


class LayerManifestError(RuntimeError):
    """Raised when a Layer Manifest artifact cannot be trusted."""


def require_safe_token(value: Any, label: str) -> str:
    """Return one portable path token, rejecting Windows aliases too."""

    if not isinstance(value, str) or not _SAFE_TOKEN.fullmatch(value):
        raise LayerManifestError(f"{label} is not safe for artifact publication")
    if value.endswith(".") or value.split(".", 1)[0].upper() in _WINDOWS_RESERVED:
        raise LayerManifestError(f"{label} uses a Windows-reserved path token")
    return value


def require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise LayerManifestError(f"{label} is not a lowercase SHA-256")
    return value


def canonical_layer_artifact_path(layer_id: Any) -> str:
    token = require_safe_token(layer_id, "Layer id")
    return f"layers/{token}.png"


def normalized_path_key(value: str) -> str:
    """Use a portable case-insensitive key even on case-sensitive hosts."""

    return value.replace("\\", "/").casefold()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def png_ihdr(path: Path) -> tuple[int, int, int, int]:
    try:
        with Path(path).open("rb") as handle:
            header = handle.read(26)
        if (
            len(header) < 26
            or header[:8] != b"\x89PNG\r\n\x1a\n"
            or header[12:16] != b"IHDR"
        ):
            raise LayerManifestError(f"Not a PNG file: {Path(path).name}")
        width, height = struct.unpack(">II", header[16:24])
        return width, height, header[24], header[25]
    except OSError as exc:
        raise LayerManifestError(f"Cannot inspect PNG: {Path(path).name}") from exc


def read_strict_manifest(bundle: Path) -> dict[str, Any]:
    bundle = _safe_bundle_directory(Path(bundle))
    path = _exact_child(bundle, "manifest.json", want_directory=False)
    try:
        if path.stat().st_size > _MAX_MANIFEST_BYTES:
            raise LayerManifestError("Layer Manifest exceeds 4 MiB")
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(
                stream,
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
    except LayerManifestError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, _StrictJsonError) as exc:
        raise LayerManifestError("Layer Manifest is not strict JSON") from exc
    if not isinstance(value, dict):
        raise LayerManifestError("Layer Manifest root must be an object")
    return value


def validate_raster_geometry(
    raster: Mapping[str, Any],
    image_size: tuple[int, int],
    manifest_canvas: tuple[int, int],
    *,
    layer_id: str,
) -> None:
    canvas = _integer_vector(raster.get("canvas_size"), 2, positive=True)
    if canvas != manifest_canvas:
        raise LayerManifestError(f"Layer {layer_id} raster canvas differs from manifest")
    bbox = _integer_vector(raster.get("crop_bbox_xywh"), 4)
    offset = _integer_vector(raster.get("canvas_offset_xy"), 2)
    x, y, width, height = bbox
    canvas_width, canvas_height = canvas
    if min(x, y, width, height) < 0:
        raise LayerManifestError(f"Layer {layer_id} crop geometry is outside its canvas")
    if x + width > canvas_width or y + height > canvas_height:
        raise LayerManifestError(f"Layer {layer_id} crop geometry is outside its canvas")
    image_width, image_height = image_size
    if (image_width, image_height) == canvas:
        if offset != (0, 0):
            raise LayerManifestError(f"Layer {layer_id} full-canvas raster has a nonzero offset")
        return
    if width < 1 or height < 1:
        raise LayerManifestError(f"Layer {layer_id} cropped raster has an empty crop")
    if (image_width, image_height) != (width, height) or offset != (x, y):
        raise LayerManifestError(
            f"Layer {layer_id} cropped raster does not match its bbox and offset"
        )


def manifest_canvas(manifest: Mapping[str, Any]) -> tuple[int, int]:
    source = manifest.get("source")
    if not isinstance(source, Mapping):
        raise LayerManifestError("Layer Manifest source is invalid")
    try:
        return _integer_vector(source.get("canvas"), 2, positive=True)
    except LayerManifestError as exc:
        raise LayerManifestError("Layer Manifest canvas is invalid") from exc


def prepare_publication(
    manifest: Mapping[str, Any],
    layer_assets: Mapping[str, Path],
    *,
    project_id: str,
) -> list[tuple[str, str, Path]]:
    if manifest.get("project_id") != project_id:
        raise LayerManifestError("Layer Manifest belongs to another project")
    canvas = manifest_canvas(manifest)
    entries = _manifest_entries(manifest)
    paths: dict[str, Path] = {}
    result: list[tuple[str, str, Path]] = []
    for layer_id, relative, raster, _layer in entries:
        source = layer_assets.get(layer_id)
        if source is None or not Path(source).is_file():
            raise LayerManifestError(f"Layer asset is missing: {layer_id}")
        source = Path(source)
        _inspect_raster(source, raster, canvas, layer_id)
        paths[layer_id] = source
        result.append((layer_id, relative, source))
    _validate_splits(manifest, paths)
    return result


def inspect_bundle_layers(
    bundle: Path, manifest: Mapping[str, Any]
) -> tuple[dict[str, tuple[int, int]], dict[str, Path]]:
    bundle = _safe_bundle_directory(Path(bundle))
    canvas = manifest_canvas(manifest)
    sizes: dict[str, tuple[int, int]] = {}
    paths: dict[str, Path] = {}
    resolved_keys: set[str] = set()
    for layer_id, relative, raster, _layer in _manifest_entries(manifest):
        image = resolve_layer_artifact(bundle, layer_id, relative)
        resolved_key = normalized_path_key(os.path.normpath(str(image.resolve())))
        if resolved_key in resolved_keys:
            raise LayerManifestError("Layer image paths resolve to the same artifact")
        resolved_keys.add(resolved_key)
        sizes[layer_id] = _inspect_raster(image, raster, canvas, layer_id)
        paths[layer_id] = image
    _validate_splits(manifest, paths)
    return sizes, paths


def safe_staging_target(staging: Path, layer_id: str, relative: str) -> Path:
    canonical = canonical_layer_artifact_path(layer_id)
    if relative != canonical:
        raise LayerManifestError(f"Layer {layer_id} image path is not canonical")
    root = _safe_bundle_directory(Path(staging))
    target = root / "layers" / f"{layer_id}.png"
    try:
        target.parent.resolve(strict=True).relative_to(root)
        target.resolve(strict=False).relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise LayerManifestError("Layer publication target escapes staging") from exc
    if target.parent.is_symlink() or target.is_symlink():
        raise LayerManifestError("Layer publication target is unsafe")
    return target


def safe_publication_parent(build_root: Path, project_id: str) -> Path:
    """Create the fixed build hierarchy without following path aliases."""

    root = Path(build_root)
    project = root / project_id
    parent = project / "layer-manifests"
    try:
        root.mkdir(parents=True, exist_ok=True)
        if root.is_symlink():
            raise LayerManifestError("Layer Manifest publication root is unsafe")
        resolved_root = root.resolve(strict=True)
        project.mkdir(exist_ok=True)
        project.resolve(strict=True).relative_to(resolved_root)
        if project.is_symlink():
            raise LayerManifestError("Layer Manifest publication root is unsafe")
        parent.mkdir(exist_ok=True)
        parent.resolve(strict=True).relative_to(resolved_root)
        if parent.is_symlink():
            raise LayerManifestError("Layer Manifest publication root is unsafe")
    except LayerManifestError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise LayerManifestError("Layer Manifest publication root is unsafe") from exc
    return parent


def resolve_layer_artifact(bundle: Path, layer_id: str, relative: str) -> Path:
    canonical = canonical_layer_artifact_path(layer_id)
    if relative != canonical:
        raise LayerManifestError(f"Layer {layer_id} image path is not canonical")
    layer_dir = _exact_child(bundle, "layers", want_directory=True)
    image = _exact_child(layer_dir, f"{layer_id}.png", want_directory=False)
    try:
        image.resolve(strict=True).relative_to(bundle.resolve(strict=True))
    except (OSError, RuntimeError, ValueError) as exc:
        raise LayerManifestError("Layer image was not found inside its bundle") from exc
    return image


def _manifest_entries(
    manifest: Mapping[str, Any],
) -> list[tuple[str, str, Mapping[str, Any], Mapping[str, Any]]]:
    layers = manifest.get("layers")
    if not isinstance(layers, list):
        raise LayerManifestError("Layer Manifest has no layer list")
    result = []
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for index, layer in enumerate(layers):
        if not isinstance(layer, Mapping) or not isinstance(layer.get("raster"), Mapping):
            raise LayerManifestError(f"Layer {index} is invalid")
        layer_id = require_safe_token(layer.get("layer_id"), f"Layer {index} id")
        relative = canonical_layer_artifact_path(layer_id)
        if layer["raster"].get("artifact_path") != relative:
            raise LayerManifestError(f"Layer {layer_id} image path is not canonical")
        id_key, path_key = layer_id.casefold(), normalized_path_key(relative)
        if id_key in seen_ids or path_key in seen_paths:
            raise LayerManifestError(f"Layer identity or image path is duplicated: {layer_id}")
        seen_ids.add(id_key)
        seen_paths.add(path_key)
        try:
            normalize_derivation(layer_id, layer.get("derivation"))
        except SplitDerivationError as exc:
            raise LayerManifestError(str(exc)) from exc
        result.append((layer_id, relative, layer["raster"], layer))
    return result


def _inspect_raster(
    image: Path,
    raster: Mapping[str, Any],
    canvas: tuple[int, int],
    layer_id: str,
) -> tuple[int, int]:
    expected = raster.get("sha256")
    if not isinstance(expected, str) or not _SHA256.fullmatch(expected):
        raise LayerManifestError(f"Layer {layer_id} image hash is invalid")
    try:
        actual = sha256_file(image)
    except (OSError, RuntimeError) as exc:
        raise LayerManifestError(f"Layer {layer_id} image is not readable") from exc
    if actual != expected:
        raise LayerManifestError(f"Layer {layer_id} image hash does not match")
    width, height, bit_depth, color_type = png_ihdr(image)
    if bit_depth != 8 or color_type != 6:
        raise LayerManifestError(f"Layer {layer_id} image is not 8-bit RGBA")
    validate_raster_geometry(raster, (width, height), canvas, layer_id=layer_id)
    return width, height


def _validate_splits(manifest: Mapping[str, Any], paths: Mapping[str, Path]) -> None:
    try:
        validate_split_bundle(manifest, paths)
    except SplitBundleValidationError as exc:
        raise LayerManifestError(str(exc)) from exc


def _safe_bundle_directory(bundle: Path) -> Path:
    try:
        resolved = bundle.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise LayerManifestError("Layer Manifest bundle was not found") from exc
    if bundle.is_symlink() or not resolved.is_dir():
        raise LayerManifestError("Layer Manifest bundle path is unsafe")
    return resolved


def _exact_child(parent: Path, name: str, *, want_directory: bool) -> Path:
    try:
        matches = [
            child
            for child in parent.iterdir()
            if child.name.casefold() == name.casefold()
        ]
    except OSError as exc:
        raise LayerManifestError("Layer Manifest bundle is incomplete") from exc
    if len(matches) != 1 or matches[0].name != name or matches[0].is_symlink():
        raise LayerManifestError(f"Bundle path is not canonical: {name}")
    child = matches[0]
    if (want_directory and not child.is_dir()) or (not want_directory and not child.is_file()):
        raise LayerManifestError(f"Bundle path has the wrong type: {name}")
    return child


def _integer_vector(value: Any, length: int, *, positive: bool = False) -> tuple[int, ...]:
    if (
        not isinstance(value, (list, tuple))
        or len(value) != length
        or any(isinstance(item, bool) or not isinstance(item, int) for item in value)
    ):
        raise LayerManifestError("Raster geometry must use exact integers")
    result = tuple(value)
    if positive and any(item < 1 for item in result):
        raise LayerManifestError("Raster size must be positive")
    return result


class _StrictJsonError(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _StrictJsonError(f"duplicate key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise _StrictJsonError(f"non-finite number: {value}")
