"""Read-only orchestration from exact P2 artifacts to an in-memory P3 rig."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any

from .manifest_artifacts import (
    canonical_layer_artifact_path,
    resolve_layer_artifact,
)
from .manifest_bundle import LayerManifestBundleReader
from .mesh_eligibility import HingeTarget, resolve_hinge_targets
from .mesh_manifest_binding import require_manifest_matches_base
from .mesh_rig import compile_mesh_rig
from .png_rgba import RgbaImage, decode_rgba_png
from .verified_base_rig import VerifiedBaseRigReader


class VerifiedMeshCompilerError(RuntimeError):
    """Raised when any trusted P3 input or compilation gate fails."""


@dataclass(frozen=True, slots=True)
class VerifiedMeshCompilation:
    """Immutable verified identities with isolated JSON result accessors."""

    project_id: str
    base_rig_sha256: str
    base_bundle_sha256: str
    manifest_sha256: str
    _compilation_json: str
    _target_image_snapshots_json: str
    _target_images: tuple[tuple[str, RgbaImage], ...] = field(repr=False)
    _target_png_bytes: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def compilation(self) -> dict[str, Any]:
        return json.loads(self._compilation_json)

    @property
    def rig(self) -> dict[str, Any]:
        return self.compilation["rig"]

    @property
    def run_manifest(self) -> dict[str, Any]:
        return self.compilation["run_manifest"]

    @property
    def targets(self) -> list[dict[str, Any]]:
        return self.compilation["targets"]

    @property
    def status(self) -> str:
        return self.compilation["status"]

    @property
    def target_image_snapshots(self) -> list[dict[str, Any]]:
        return json.loads(self._target_image_snapshots_json)

    @property
    def target_images(self) -> dict[str, RgbaImage]:
        return dict(self._target_images)

    @property
    def target_png_bytes(self) -> dict[str, bytes]:
        return dict(self._target_png_bytes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "base_rig_sha256": self.base_rig_sha256,
            "base_bundle_sha256": self.base_bundle_sha256,
            "manifest_sha256": self.manifest_sha256,
            "compilation": self.compilation,
            "target_image_snapshots": self.target_image_snapshots,
        }


class VerifiedMeshCompiler:
    """Compile only exact content-addressed inputs, without publishing output."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)

    def compile(
        self,
        project_id: str,
        base_rig_sha256: str,
        base_bundle_sha256: str,
    ) -> VerifiedMeshCompilation:
        try:
            base = VerifiedBaseRigReader(self.state_root).load(
                project_id, base_rig_sha256, base_bundle_sha256
            )
            base_rig, base_run = base.rig, base.run_manifest
            source = _object(base_rig.get("source"), "base RigIR source")
            manifest_sha = source.get("layer_manifest_sha256")
            manifest_bundle = LayerManifestBundleReader(self.state_root).load(
                project_id, manifest_sha
            )
            require_manifest_matches_base(
                manifest_bundle.manifest,
                base_rig,
                base_run,
                manifest_bundle.image_sizes,
            )
            targets = resolve_hinge_targets(manifest_bundle.manifest, base_rig)
            images, png_bytes, snapshots = _load_target_images(
                manifest_bundle, targets
            )
            compilation = compile_mesh_rig(
                base_rig,
                base_run,
                manifest_bundle.manifest,
                images,
                base_bundle_sha256=base.bundle_sha256,
            )
            return VerifiedMeshCompilation(
                project_id=project_id,
                base_rig_sha256=base.rig_sha256,
                base_bundle_sha256=base.bundle_sha256,
                manifest_sha256=manifest_bundle.sha256,
                _compilation_json=_encode(compilation.to_dict()),
                _target_image_snapshots_json=_encode(snapshots),
                _target_images=tuple(images.items()),
                _target_png_bytes=tuple(png_bytes.items()),
            )
        except VerifiedMeshCompilerError:
            raise
        except (OSError, RuntimeError, TypeError, ValueError, KeyError) as exc:
            raise VerifiedMeshCompilerError(
                f"Verified mesh compilation failed: {exc}"
            ) from exc


def _load_target_images(
    bundle: Any,
    targets: tuple[HingeTarget, ...],
) -> tuple[
    dict[str, RgbaImage], dict[str, bytes], list[dict[str, Any]]
]:
    layers = _layers_by_id(bundle.manifest)
    images: dict[str, RgbaImage] = {}
    png_bytes: dict[str, bytes] = {}
    snapshots: list[dict[str, Any]] = []
    for target in targets:
        layer = layers.get(target.source_layer_id)
        if layer is None:
            raise VerifiedMeshCompilerError(
                f"Mesh target layer is missing: {target.source_layer_id}"
            )
        raster = _object(layer.get("raster"), "target raster")
        relative = canonical_layer_artifact_path(target.source_layer_id)
        if raster.get("artifact_path") != relative:
            raise VerifiedMeshCompilerError("Mesh target image path is not canonical")
        path = resolve_layer_artifact(
            bundle.path, target.source_layer_id, relative
        )
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise VerifiedMeshCompilerError(
                f"Cannot read mesh target image: {target.source_layer_id}"
            ) from exc
        digest = hashlib.sha256(data).hexdigest()
        if digest != raster.get("sha256"):
            raise VerifiedMeshCompilerError(
                f"Mesh target image hash changed: {target.source_layer_id}"
            )
        image = decode_rgba_png(data, source_name=relative)
        expected_size = bundle.image_sizes.get(target.source_layer_id)
        if expected_size != (image.width, image.height):
            raise VerifiedMeshCompilerError(
                f"Mesh target image size changed: {target.source_layer_id}"
            )
        images[target.attachment_id] = image
        png_bytes[target.attachment_id] = data
        snapshots.append({
            "attachment_id": target.attachment_id,
            "source_layer_id": target.source_layer_id,
            "artifact_path": relative,
            "sha256": digest,
            "byte_length": len(data),
            "width": image.width,
            "height": image.height,
        })
    return images, png_bytes, snapshots


def _layers_by_id(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    layers = manifest.get("layers")
    if not isinstance(layers, list):
        raise VerifiedMeshCompilerError("Layer Manifest layers must be an array")
    for layer in layers:
        layer = _object(layer, "Layer Manifest layer")
        layer_id = layer.get("layer_id")
        if not isinstance(layer_id, str) or layer_id in result:
            raise VerifiedMeshCompilerError("Layer Manifest target ids are invalid")
        result[layer_id] = layer
    return result


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise VerifiedMeshCompilerError(f"{label} must be an object")
    return value


def _encode(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
