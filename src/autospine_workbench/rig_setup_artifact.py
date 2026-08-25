"""Canonical setup PNG and its renderer/encoder identity contract."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Mapping

from .manifest_artifacts import (
    LayerManifestError,
    require_safe_token,
    require_sha256,
)
from .png_rgba import RgbaImage, RgbaPngError, encode_rgba_png
from .resolved_project import canonical_sha256
from .rig_setup_render import RigSetupRenderError, render_rig_setup


SETUP_DOCUMENT_NAME = "setup-render.json"
SETUP_IMAGE_NAME = "setup.png"
RENDERER_ID = "autospine-region-setup-renderer"
RENDERER_VERSION = "1.0.0"
ENCODER_ID = "autospine-canonical-rgba-png"
ENCODER_VERSION = "1.0.0"
ENCODER_PROFILE = "rgba8-filter0-stored-deflate"
_RENDERER_DISPATCH = {
    (RENDERER_ID, RENDERER_VERSION): render_rig_setup,
}


class RigSetupArtifactError(RuntimeError):
    """Raised when setup pixels and their immutable contract differ."""


@dataclass(frozen=True, slots=True)
class RigSetupArtifact:
    document: dict[str, Any]
    png: bytes

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.document)


def renderer_identity() -> dict[str, str]:
    return {"id": RENDERER_ID, "version": RENDERER_VERSION}


def encoder_identity() -> dict[str, str]:
    return {
        "id": ENCODER_ID,
        "version": ENCODER_VERSION,
        "profile": ENCODER_PROFILE,
    }


def build_setup_artifact(
    project_id: str,
    rig: Mapping[str, Any],
    rig_sha256: str,
    layer_bundle_path: Path,
) -> RigSetupArtifact:
    return _build_setup_artifact(
        project_id,
        rig,
        rig_sha256,
        layer_bundle_path,
        renderer_identity(),
    )


def _build_setup_artifact(
    project_id: str,
    rig: Mapping[str, Any],
    rig_sha256: str,
    layer_bundle_path: Path,
    renderer: Mapping[str, Any],
) -> RigSetupArtifact:
    try:
        project_id = require_safe_token(project_id, "Project id")
        rig_sha = require_sha256(rig_sha256, "RigIR")
        if canonical_sha256(rig) != rig_sha:
            raise RigSetupArtifactError("RigIR content does not match its SHA-256")
        source = _mapping(rig.get("source"), "RigIR source")
        layer_sha = require_sha256(
            source.get("layer_manifest_sha256"), "Layer Manifest"
        )
        canvas = _mapping(rig.get("canvas"), "RigIR canvas")
        width, height = canvas.get("width"), canvas.get("height")
        rgba = _render_setup(renderer, rig, Path(layer_bundle_path))
        image = RgbaImage(_positive_int(width), _positive_int(height), rgba)
        png = encode_rgba_png(image)
    except RigSetupArtifactError:
        raise
    except (
        LayerManifestError,
        RgbaPngError,
        RigSetupRenderError,
        TypeError,
        ValueError,
    ) as exc:
        raise RigSetupArtifactError("Could not build canonical setup PNG") from exc
    document = {
        "format": "autospine-rig-setup-render",
        "format_version": 1,
        "project_id": project_id,
        "source": {
            "rig_sha256": rig_sha,
            "layer_manifest_sha256": layer_sha,
        },
        "renderer": dict(renderer),
        "encoder": encoder_identity(),
        "image": {
            "path": SETUP_IMAGE_NAME,
            "width": image.width,
            "height": image.height,
            "rgba_sha256": hashlib.sha256(rgba).hexdigest(),
            "png_sha256": hashlib.sha256(png).hexdigest(),
        },
    }
    return RigSetupArtifact(document=document, png=png)


def verify_setup_artifact(
    document: Mapping[str, Any],
    png: bytes,
    *,
    project_id: str,
    rig: Mapping[str, Any],
    rig_sha256: str,
    bundle_path: Path,
) -> RigSetupArtifact:
    _validate_document_shape(document)
    expected = _build_setup_artifact(
        project_id,
        rig,
        rig_sha256,
        bundle_path,
        _mapping(document.get("renderer"), "setup renderer"),
    )
    if dict(document) != expected.document:
        raise RigSetupArtifactError("Setup render contract differs from canonical output")
    if not isinstance(png, bytes) or png != expected.png:
        raise RigSetupArtifactError("Setup PNG differs from canonical output")
    return expected


def _validate_document_shape(value: Mapping[str, Any]) -> None:
    _exact(value, {"format", "format_version", "project_id", "source", "renderer", "encoder", "image"}, "setup render")
    if value.get("format") != "autospine-rig-setup-render" or value.get("format_version") != 1:
        raise RigSetupArtifactError("Setup render format is unsupported")
    try:
        require_safe_token(value.get("project_id"), "Project id")
    except LayerManifestError as exc:
        raise RigSetupArtifactError("Setup render project id is invalid") from exc
    source = _mapping(value.get("source"), "setup source")
    _exact(source, {"rig_sha256", "layer_manifest_sha256"}, "setup source")
    renderer = _mapping(value.get("renderer"), "setup renderer")
    encoder = _mapping(value.get("encoder"), "setup encoder")
    image = _mapping(value.get("image"), "setup image")
    _exact(renderer, set(renderer_identity()), "setup renderer")
    _exact(encoder, set(encoder_identity()), "setup encoder")
    _exact(image, {"path", "width", "height", "rgba_sha256", "png_sha256"}, "setup image")
    _renderer(renderer)
    if dict(encoder) != encoder_identity():
        raise RigSetupArtifactError("Setup encoder identity is unsupported")


def _render_setup(
    identity: Mapping[str, Any], rig: Mapping[str, Any], bundle: Path
) -> bytes:
    return _renderer(identity)(rig, bundle)


def _renderer(identity: Mapping[str, Any]):
    key = (identity.get("id"), identity.get("version"))
    renderer = _RENDERER_DISPATCH.get(key)
    if renderer is None:
        raise RigSetupArtifactError("Setup renderer identity is unsupported")
    return renderer


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RigSetupArtifactError(f"{label} must be an object")
    return value


def _exact(value: Mapping[str, Any], keys: set[str], label: str) -> None:
    if set(value) != keys:
        raise RigSetupArtifactError(f"{label} fields are incomplete or unsupported")


def _positive_int(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise RigSetupArtifactError("Setup dimensions must be positive integers")
    return value
