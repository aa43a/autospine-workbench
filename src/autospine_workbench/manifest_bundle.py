"""Strict read boundary for immutable Layer Manifest bundles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .manifest_artifacts import (
    LayerManifestError,
    inspect_bundle_layers,
    read_strict_manifest,
    require_safe_token,
    require_sha256,
)
from .resolved_project import canonical_sha256


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
        try:
            project_id = require_safe_token(project_id, "Project id")
            digest = require_sha256(digest, "Layer Manifest digest")
        except LayerManifestError as exc:
            raise LayerManifestBundleError("Layer Manifest bundle identity is invalid") from exc
        bundle = self._resolve_bundle(project_id, digest)
        try:
            manifest = read_strict_manifest(bundle)
        except LayerManifestError as exc:
            raise LayerManifestBundleError(str(exc)) from exc
        if canonical_sha256(manifest) != digest:
            raise LayerManifestBundleError("Layer Manifest does not match its content address")
        if manifest.get("project_id") != project_id:
            raise LayerManifestBundleError("Layer Manifest belongs to another project")
        image_sizes, _image_paths = self._verify_layers(bundle, manifest)
        return LoadedLayerManifestBundle(bundle, digest, manifest, image_sizes)

    def _resolve_bundle(self, project_id: str, digest: str) -> Path:
        lexical_project = self.root / project_id
        lexical_root = lexical_project / "layer-manifests"
        lexical_bundle = lexical_root / digest
        try:
            builds = self.root.resolve(strict=True)
            root = lexical_root.resolve(strict=True)
            bundle = lexical_bundle.resolve(strict=True)
            root.relative_to(builds)
            bundle.relative_to(root)
        except (OSError, RuntimeError, ValueError) as exc:
            raise LayerManifestBundleError("Layer Manifest bundle was not found") from exc
        unsafe = any(
            path.is_symlink()
            for path in (self.root, lexical_project, lexical_root, lexical_bundle)
        )
        if unsafe or not bundle.is_dir():
            raise LayerManifestBundleError("Layer Manifest bundle path is unsafe")
        return bundle

    @staticmethod
    def _verify_layers(
        bundle: Path, manifest: dict[str, Any]
    ) -> tuple[dict[str, tuple[int, int]], dict[str, Path]]:
        try:
            return inspect_bundle_layers(bundle, manifest)
        except LayerManifestError as exc:
            raise LayerManifestBundleError(str(exc)) from exc
