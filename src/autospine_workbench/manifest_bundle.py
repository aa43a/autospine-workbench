"""Strict read boundary for immutable Layer Manifest bundles."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from .layer_manifest import _png_ihdr, sha256_file
from .resolved_project import canonical_sha256


_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_MANIFEST_BYTES = 4 * 1024 * 1024


class LayerManifestBundleError(RuntimeError):
    """Raised when a published manifest bundle cannot be trusted."""


@dataclass(frozen=True, slots=True)
class LoadedLayerManifestBundle:
    path: Path
    sha256: str
    manifest: dict[str, Any]
    image_sizes: dict[str, tuple[int, int]]


class LayerManifestBundleReader:
    """Load one exact bundle without following aliases or symbolic links."""

    def __init__(self, state_root: Path) -> None:
        self.root = Path(state_root) / "builds"

    def load(self, project_id: str, digest: str) -> LoadedLayerManifestBundle:
        if not _SAFE_TOKEN.fullmatch(project_id) or not _SHA256.fullmatch(digest):
            raise LayerManifestBundleError("Layer Manifest bundle identity is invalid")
        bundle = self._resolve_bundle(project_id, digest)
        manifest = _read_manifest(bundle / "manifest.json")
        if canonical_sha256(manifest) != digest:
            raise LayerManifestBundleError("Layer Manifest does not match its content address")
        if manifest.get("project_id") != project_id:
            raise LayerManifestBundleError("Layer Manifest belongs to another project")
        image_sizes = self._verify_layers(bundle, manifest)
        return LoadedLayerManifestBundle(bundle, digest, manifest, image_sizes)

    def _resolve_bundle(self, project_id: str, digest: str) -> Path:
        lexical_root = self.root / project_id / "layer-manifests"
        lexical_bundle = lexical_root / digest
        try:
            root = lexical_root.resolve(strict=True)
            bundle = lexical_bundle.resolve(strict=True)
            bundle.relative_to(root)
        except (OSError, ValueError) as exc:
            raise LayerManifestBundleError("Layer Manifest bundle was not found") from exc
        if lexical_root.is_symlink() or lexical_bundle.is_symlink() or not bundle.is_dir():
            raise LayerManifestBundleError("Layer Manifest bundle path is unsafe")
        return bundle

    @staticmethod
    def _verify_layers(
        bundle: Path, manifest: dict[str, Any]
    ) -> dict[str, tuple[int, int]]:
        layers = manifest.get("layers")
        if not isinstance(layers, list):
            raise LayerManifestBundleError("Layer Manifest has no layer list")
        sizes: dict[str, tuple[int, int]] = {}
        seen_paths: set[str] = set()
        for index, layer in enumerate(layers):
            if not isinstance(layer, dict) or not isinstance(layer.get("raster"), dict):
                raise LayerManifestBundleError(f"Layer {index} is invalid")
            layer_id = layer.get("layer_id")
            relative = layer["raster"].get("artifact_path")
            expected = layer["raster"].get("sha256")
            if not isinstance(layer_id, str) or not _SAFE_TOKEN.fullmatch(layer_id):
                raise LayerManifestBundleError(f"Layer {index} has an unsafe id")
            if not _safe_relative_path(relative) or relative in seen_paths:
                raise LayerManifestBundleError(f"Layer {layer_id} has an unsafe image path")
            seen_paths.add(relative)
            image = _resolve_file(bundle, relative)
            if not isinstance(expected, str) or sha256_file(image) != expected:
                raise LayerManifestBundleError(f"Layer {layer_id} image hash does not match")
            try:
                width, height, bit_depth, color_type = _png_ihdr(image)
            except RuntimeError as exc:
                raise LayerManifestBundleError(f"Layer {layer_id} image is not readable") from exc
            if bit_depth != 8 or color_type != 6:
                raise LayerManifestBundleError(f"Layer {layer_id} image is not 8-bit RGBA")
            sizes[layer_id] = (width, height)
        return sizes


def _read_manifest(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise LayerManifestBundleError("Layer Manifest path is unsafe")
    try:
        if path.stat().st_size > _MAX_MANIFEST_BYTES:
            raise LayerManifestBundleError("Layer Manifest exceeds 4 MiB")
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(
                stream,
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
    except LayerManifestBundleError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, _StrictJsonError) as exc:
        raise LayerManifestBundleError("Layer Manifest is not strict JSON") from exc
    if not isinstance(value, dict):
        raise LayerManifestBundleError("Layer Manifest root must be an object")
    return value


def _resolve_file(bundle: Path, relative: str) -> Path:
    lexical = bundle / relative
    try:
        resolved = lexical.resolve(strict=True)
        resolved.relative_to(bundle)
    except (OSError, ValueError) as exc:
        raise LayerManifestBundleError("Layer image was not found inside its bundle") from exc
    if lexical.is_symlink() or not resolved.is_file():
        raise LayerManifestBundleError("Layer image path is unsafe")
    return resolved


def _safe_relative_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        return False
    path = Path(value)
    return not path.is_absolute() and not path.drive and ".." not in path.parts


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
