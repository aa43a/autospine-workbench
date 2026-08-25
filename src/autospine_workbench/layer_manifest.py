"""Build and publish immutable, region-first Layer Manifest bundles."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import tempfile
from typing import Any, Mapping

from .resolved_project import canonical_sha256
from .rig_roles import region_bone_for_role


class LayerManifestError(RuntimeError):
    """Raised when a reviewed project cannot be materialized losslessly."""


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class LayerManifestBuilder:
    def build(
        self,
        project: Mapping[str, Any],
        layer_assets: Mapping[str, Path],
    ) -> dict[str, Any]:
        resolved = project.get("resolved")
        if not isinstance(resolved, Mapping):
            raise LayerManifestError("Project has no resolved snapshot")
        canvas = resolved.get("canvas") or project.get("canvas") or {}
        width, height = int(canvas.get("width", 0)), int(canvas.get("height", 0))
        if width < 1 or height < 1:
            raise LayerManifestError("Canvas dimensions are invalid")
        source = project.get("source") or {}
        psd_sha = _required_sha(source.get("sha256"), "source PSD")
        audit_sha = _required_sha(source.get("audit_sha256"), "audit")

        layers: list[dict[str, Any]] = []
        aggregate_flags: set[str] = set()
        for layer in resolved.get("layers", []):
            if not isinstance(layer, Mapping):
                continue
            layer_id = str(layer.get("id"))
            if not _SAFE_ID.fullmatch(layer_id):
                raise LayerManifestError("Layer id is not safe for artifact publication")
            asset = layer_assets.get(layer_id)
            if asset is None or not Path(asset).is_file():
                raise LayerManifestError(f"Layer asset is missing: {layer_id}")
            asset = Path(asset)
            image_width, image_height, bit_depth, color_type = _png_ihdr(asset)
            if bit_depth != 8 or color_type != 6:
                raise LayerManifestError(
                    f"Layer {layer_id} must be an 8-bit RGBA PNG; got depth={bit_depth}, type={color_type}"
                )
            bbox = layer.get("bbox") or {}
            bbox_xywh = [
                int(bbox.get("x", 0)),
                int(bbox.get("y", 0)),
                int(bbox.get("width", 0)),
                int(bbox.get("height", 0)),
            ]
            if (image_width, image_height) == (width, height):
                offset = [0, 0]
            elif (image_width, image_height) == tuple(bbox_xywh[2:]):
                offset = bbox_xywh[:2]
            else:
                raise LayerManifestError(
                    f"Layer {layer_id} dimensions do not match canvas or alpha bbox"
                )
            flags = _layer_flags(layer)
            aggregate_flags.update(flags)
            manual = layer.get("review_state") == "manual_adjusted"
            excluded = layer.get("disposition") == "exclude" or bool(layer.get("empty"))
            pivot_xy = layer.get("pivot_xy")
            layers.append(
                {
                    "layer_id": layer_id,
                    "source": {
                        "name": str(layer.get("name") or layer_id),
                        "index": int(layer.get("source_index", layer.get("z_index", 0))),
                        "group_path": [],
                        "visible": bool(layer.get("visible")),
                        "opacity": float(layer.get("opacity", 1)),
                        "blend_mode": _blend_mode(layer.get("blend_mode")),
                    },
                    "raster": {
                        "artifact_path": f"layers/{layer_id}.png",
                        "sha256": sha256_file(asset),
                        "canvas_size": [width, height],
                        "crop_bbox_xywh": bbox_xywh,
                        "canvas_offset_xy": offset,
                        "channels": "RGBA",
                        "alpha_mode": "straight",
                        "color_space": "srgb",
                        "alpha_nonzero": int((layer.get("metrics") or {}).get("alpha_nonzero", 0)),
                    },
                    "semantic": {
                        "source_tag": str(layer.get("name") or ""),
                        "canonical_role": str(layer.get("canonical_role") or "unclassified.layer"),
                        "side": str(layer.get("side") or "unknown"),
                        "stratum": _stratum(str(layer.get("canonical_role") or "")),
                        "instance": 0,
                        "mapping_method": "manual" if manual else "alias",
                        "confidence": 1.0 if manual else 0.5,
                    },
                    "derivation": {"operation": "source", "parent_layer_ids": []},
                    "rig_hint": {
                        "attachment_kind": "excluded" if excluded else "region",
                        "deform_class": _deform_class(str(layer.get("canonical_role") or "")),
                        "candidate_bone": _candidate_bone(str(layer.get("canonical_role") or ""), str(layer.get("side") or "unknown")),
                        "pivot": (
                            {
                                "xy": [float(pivot_xy[0]), float(pivot_xy[1])],
                                "method": "manual" if manual else "unknown",
                                "confidence": 1.0 if manual else 0.25,
                            }
                            if isinstance(pivot_xy, (list, tuple)) and len(pivot_xy) == 2
                            else None
                        ),
                        "setup_draw_order": int(layer.get("z_index", 0)),
                    },
                    "qa": {
                        "status": "manual_required" if flags else "passed",
                        "flags": flags,
                        "notes": [str(layer.get("notes"))] if layer.get("notes") else [],
                    },
                }
            )
        return {
            "format": "autospine-layer-manifest",
            "format_version": 1,
            "project_id": str(project.get("id")),
            "revision": int(resolved.get("revision", 0)),
            "source": {
                "psd_sha256": psd_sha,
                "audit_sha256": audit_sha,
                "canvas": [width, height],
                "coordinate_system": {
                    "origin": "top_left",
                    "x_axis": "right",
                    "y_axis": "down",
                    "units": "pixel",
                    "side_naming": "character_side",
                    "view_orientation": "unknown",
                    "mirror_state": "unknown",
                },
            },
            "layers": layers,
            "qa": {
                "status": "manual_required" if aggregate_flags else "passed",
                "flags": sorted(aggregate_flags),
                "notes": [],
            },
        }


class LayerManifestBundleStore:
    """Publish manifest + layer PNGs as one content-addressed directory."""

    def __init__(self, state_root: Path) -> None:
        self.root = Path(state_root) / "builds"

    def publish(
        self,
        project_id: str,
        manifest: Mapping[str, Any],
        layer_assets: Mapping[str, Path],
    ) -> tuple[Path, str]:
        if not _SAFE_ID.fullmatch(project_id):
            raise LayerManifestError("Project id is not safe for artifact publication")
        digest = canonical_sha256(manifest)
        parent = self.root / project_id / "layer-manifests"
        destination = parent / digest
        parent.mkdir(parents=True, exist_ok=True)
        if destination.is_dir():
            self._verify(destination, digest)
            return destination, digest
        staging: Path | None = Path(
            tempfile.mkdtemp(prefix=f".{digest[:12]}.", dir=parent)
        )
        try:
            assert staging is not None
            layer_dir = staging / "layers"
            layer_dir.mkdir()
            for layer in manifest.get("layers", []):
                layer_id = layer["layer_id"]
                source = Path(layer_assets[layer_id])
                target = staging / layer["raster"]["artifact_path"]
                shutil.copyfile(source, target)
                _fsync_file(target)
                if sha256_file(target) != layer["raster"]["sha256"]:
                    raise LayerManifestError(f"Layer changed while copying: {layer_id}")
            manifest_path = staging / "manifest.json"
            encoded = (
                json.dumps(manifest, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
                + "\n"
            )
            with manifest_path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.rename(staging, destination)
                staging = None
            except OSError:
                if not destination.is_dir():
                    raise
                self._verify(destination, digest)
        except LayerManifestError:
            raise
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise LayerManifestError("Could not publish layer manifest bundle") from exc
        finally:
            if staging is not None and staging.is_dir():
                shutil.rmtree(staging)
        return destination, digest

    @staticmethod
    def _verify(directory: Path, expected_digest: str) -> None:
        try:
            manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
            if canonical_sha256(manifest) != expected_digest:
                raise LayerManifestError("Existing manifest has the wrong content address")
            for layer in manifest["layers"]:
                path = directory / layer["raster"]["artifact_path"]
                if sha256_file(path) != layer["raster"]["sha256"]:
                    raise LayerManifestError(f"Existing layer hash mismatch: {layer['layer_id']}")
        except (OSError, KeyError, json.JSONDecodeError) as exc:
            raise LayerManifestError("Existing manifest bundle is incomplete") from exc


def _required_sha(value: Any, label: str) -> str:
    value = str(value or "")
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise LayerManifestError(f"Missing or invalid {label} SHA-256")
    return value


def _png_ihdr(path: Path) -> tuple[int, int, int, int]:
    try:
        with path.open("rb") as handle:
            header = handle.read(26)
        if len(header) < 26 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
            raise LayerManifestError(f"Not a PNG file: {path.name}")
        width, height = struct.unpack(">II", header[16:24])
        return width, height, header[24], header[25]
    except OSError as exc:
        raise LayerManifestError(f"Cannot inspect PNG: {path.name}") from exc


def _fsync_file(path: Path) -> None:
    with path.open("r+b") as handle:
        os.fsync(handle.fileno())


def _layer_flags(layer: Mapping[str, Any]) -> list[str]:
    flags: list[str] = []
    if layer.get("empty"):
        flags.append("EMPTY_LAYER")
    if str(layer.get("canonical_role") or "").startswith("unclassified"):
        flags.append("UNCLASSIFIED_ROLE")
    if layer.get("disposition") == "review":
        flags.append("LAYER_REVIEW_REQUIRED")
    if int((layer.get("metrics") or {}).get("component_count", 0)) > 1:
        flags.append("MULTIPLE_ALPHA_COMPONENTS")
    return flags


def _blend_mode(value: Any) -> str:
    token = str(value or "normal").lower()
    return token.removeprefix("blendmode.")


def _stratum(role: str) -> str:
    if role == "hair.back":
        return "back"
    if role == "hair.front" or role.startswith("face."):
        return "front"
    return "body" if role else "unknown"


def _deform_class(role: str) -> str:
    if role.startswith("hair"):
        return "hair"
    if role.startswith("face"):
        return "face"
    if role.startswith("body.arm") or role.startswith("body.leg"):
        return "hinge"
    if role.startswith("body") or role.startswith("accessory"):
        return "rigid"
    return "unknown"


def _candidate_bone(role: str, side: str) -> str | None:
    return region_bone_for_role(role, side)
