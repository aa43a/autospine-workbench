"""Build and publish immutable, region-first Layer Manifest bundles."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
from typing import Any, Mapping, Sequence

from .atomic_staging import create_same_parent_staging
from .manifest_artifacts import (
    LayerManifestError,
    canonical_layer_artifact_path,
    inspect_bundle_layers,
    png_ihdr,
    prepare_publication,
    read_strict_manifest,
    safe_publication_parent,
    require_safe_token,
    safe_staging_target,
    sha256_file,
    validate_raster_geometry,
)
from .resolved_project import canonical_sha256
from .resolved_snapshot_validation import (
    ResolvedSnapshotValidationError,
    require_resolved_snapshot_for_project,
)
from .rig_roles import region_bone_for_role
from .split_bundle_validation import SplitBundleValidationError, validate_split_bundle
from .split_derivation_contract import SplitDerivationError, normalize_derivation


# Backwards-compatible private alias used by older callers during P2 migration.
_png_ihdr = png_ihdr


class LayerManifestBuilder:
    def build(
        self,
        project: Mapping[str, Any],
        layer_assets: Mapping[str, Path],
        *,
        materialized_layers: Sequence[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        resolved = project.get("resolved")
        if not isinstance(resolved, Mapping):
            raise LayerManifestError("Project has no resolved snapshot")
        project_id = require_safe_token(project.get("id"), "Project id")
        try:
            require_resolved_snapshot_for_project(resolved, project)
        except ResolvedSnapshotValidationError as exc:
            raise LayerManifestError(f"Resolved project is invalid: {exc}") from exc
        canvas = resolved.get("canvas") or project.get("canvas") or {}
        width, height = int(canvas.get("width", 0)), int(canvas.get("height", 0))
        if width < 1 or height < 1:
            raise LayerManifestError("Canvas dimensions are invalid")
        source = project.get("source") or {}
        psd_sha = _required_sha(source.get("sha256"), "source PSD")
        audit_sha = _required_sha(source.get("audit_sha256"), "audit")

        source_layers: Any = (
            resolved.get("layers", [])
            if materialized_layers is None
            else materialized_layers
        )
        if not isinstance(source_layers, Sequence) or isinstance(
            source_layers, (str, bytes, bytearray)
        ):
            raise LayerManifestError("Materialized layers must be an array")
        layers: list[dict[str, Any]] = []
        seen_layer_ids: set[str] = set()
        aggregate_flags: set[str] = set()
        for layer in source_layers:
            if not isinstance(layer, Mapping):
                raise LayerManifestError("Materialized layer entries must be objects")
            layer_id = require_safe_token(layer.get("id"), "Layer id")
            identity_key = layer_id.casefold()
            if identity_key in seen_layer_ids:
                raise LayerManifestError(f"Layer id is duplicated: {layer_id}")
            seen_layer_ids.add(identity_key)
            asset = layer_assets.get(layer_id)
            if asset is None or not Path(asset).is_file():
                raise LayerManifestError(f"Layer asset is missing: {layer_id}")
            asset = Path(asset)
            image_width, image_height, bit_depth, color_type = png_ihdr(asset)
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
            reviewed_fields = {
                field for field in layer.get("reviewed_fields", []) if isinstance(field, str)
            }
            semantic_manual = {"canonical_role", "side"}.issubset(reviewed_fields)
            pivot_manual = "pivot_xy" in reviewed_fields
            excluded = layer.get("disposition") == "exclude" or bool(layer.get("empty"))
            pivot_xy = layer.get("pivot_xy")
            proposed_bone = layer.get("proposed_candidate_bone")
            candidate_bone_reviewed = "candidate_bone" in reviewed_fields
            if candidate_bone_reviewed:
                candidate_bone = layer.get("candidate_bone")
            elif proposed_bone is not None:
                candidate_bone = require_safe_token(
                    proposed_bone, f"Layer {layer_id} proposed candidate bone"
                )
            else:
                candidate_bone = _candidate_bone(
                    str(layer.get("canonical_role") or ""),
                    str(layer.get("side") or "unknown"),
                )
            flags = _layer_flags(
                layer,
                excluded=excluded,
                semantic_manual=semantic_manual,
                pivot_manual=pivot_manual,
                candidate_bone=candidate_bone,
                candidate_bone_proposed=(
                    proposed_bone is not None and not candidate_bone_reviewed
                ),
                reviewed_fields=reviewed_fields,
            )
            aggregate_flags.update(flags)
            try:
                derivation = normalize_derivation(layer_id, layer.get("derivation"))
            except SplitDerivationError as exc:
                raise LayerManifestError(str(exc)) from exc
            raster = {
                "artifact_path": canonical_layer_artifact_path(layer_id),
                "sha256": sha256_file(asset),
                "canvas_size": [width, height],
                "crop_bbox_xywh": bbox_xywh,
                "canvas_offset_xy": offset,
                "channels": "RGBA",
                "alpha_mode": "straight",
                "color_space": "srgb",
                "alpha_nonzero": int(
                    (layer.get("metrics") or {}).get("alpha_nonzero", 0)
                ),
            }
            validate_raster_geometry(
                raster,
                (image_width, image_height),
                (width, height),
                layer_id=layer_id,
            )
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
                    "raster": raster,
                    "semantic": {
                        "source_tag": str(layer.get("name") or ""),
                        "canonical_role": str(layer.get("canonical_role") or "unclassified.layer"),
                        "side": str(layer.get("side") or "unknown"),
                        "stratum": _stratum(str(layer.get("canonical_role") or "")),
                        "instance": 0,
                        "mapping_method": "manual" if semantic_manual else "alias",
                        "confidence": 1.0 if semantic_manual else 0.5,
                    },
                    "derivation": derivation,
                    "rig_hint": {
                        "attachment_kind": "excluded" if excluded else "region",
                        "deform_class": _deform_class(str(layer.get("canonical_role") or "")),
                        "candidate_bone": candidate_bone,
                        "pivot": (
                            {
                                "xy": [float(pivot_xy[0]), float(pivot_xy[1])],
                                "method": "manual" if pivot_manual else "unknown",
                                "confidence": 1.0 if pivot_manual else 0.25,
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
        manifest = {
            "format": "autospine-layer-manifest",
            "format_version": 1,
            "project_id": project_id,
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
        try:
            validate_split_bundle(
                manifest,
                {
                    layer["layer_id"]: Path(layer_assets[layer["layer_id"]])
                    for layer in layers
                },
            )
        except (KeyError, SplitBundleValidationError) as exc:
            raise LayerManifestError(str(exc)) from exc
        return manifest


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
        project_id = require_safe_token(project_id, "Project id")
        entries = prepare_publication(manifest, layer_assets, project_id=project_id)
        digest = canonical_sha256(manifest)
        parent = safe_publication_parent(self.root, project_id)
        destination = parent / digest
        if destination.exists() or destination.is_symlink():
            self._verify(destination, digest, project_id)
            return destination, digest
        staging: Path | None = create_same_parent_staging(
            parent, prefix=f".{digest[:12]}.",
        )
        try:
            assert staging is not None
            layer_dir = staging / "layers"
            layer_dir.mkdir()
            rasters = {layer["layer_id"]: layer["raster"] for layer in manifest["layers"]}
            for layer_id, relative, source in entries:
                target = safe_staging_target(staging, layer_id, relative)
                shutil.copyfile(source, target)
                _fsync_file(target)
                if sha256_file(target) != rasters[layer_id]["sha256"]:
                    raise LayerManifestError(f"Layer changed while copying: {layer_id}")
            inspect_bundle_layers(staging, manifest)
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
                if not destination.exists() and not destination.is_symlink():
                    raise
                self._verify(destination, digest, project_id)
        except LayerManifestError:
            raise
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise LayerManifestError("Could not publish layer manifest bundle") from exc
        finally:
            if staging is not None and staging.is_dir():
                shutil.rmtree(staging)
        return destination, digest

    @staticmethod
    def _verify(directory: Path, expected_digest: str, project_id: str) -> None:
        manifest = read_strict_manifest(directory)
        if canonical_sha256(manifest) != expected_digest:
            raise LayerManifestError("Existing manifest has the wrong content address")
        if manifest.get("project_id") != project_id:
            raise LayerManifestError("Existing manifest belongs to another project")
        inspect_bundle_layers(directory, manifest)


def _required_sha(value: Any, label: str) -> str:
    value = str(value or "")
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise LayerManifestError(f"Missing or invalid {label} SHA-256")
    return value


def _fsync_file(path: Path) -> None:
    with path.open("r+b") as handle:
        os.fsync(handle.fileno())


def _layer_flags(
    layer: Mapping[str, Any],
    *,
    excluded: bool,
    semantic_manual: bool,
    pivot_manual: bool,
    candidate_bone: Any,
    candidate_bone_proposed: bool,
    reviewed_fields: set[str],
) -> list[str]:
    flags: list[str] = []
    if layer.get("empty") and not excluded:
        flags.append("EMPTY_LAYER")
    if not excluded and str(layer.get("canonical_role") or "").startswith("unclassified"):
        flags.append("UNCLASSIFIED_ROLE")
    if layer.get("disposition") == "review":
        flags.append("LAYER_REVIEW_REQUIRED")
    accepted_components = (
        "disposition" in reviewed_fields and layer.get("disposition") == "keep"
    )
    if not excluded and int((layer.get("metrics") or {}).get("component_count", 0)) > 1 and not accepted_components:
        flags.append("MULTIPLE_ALPHA_COMPONENTS")
    if not excluded and layer.get("disposition") in {"split", "split_left_right"}:
        flags.append("SPLIT_NOT_MATERIALIZED")
    if not excluded and not semantic_manual:
        flags.append("SEMANTIC_REVIEW_REQUIRED")
    if not excluded and not pivot_manual:
        flags.append("PIVOT_REVIEW_REQUIRED")
    if not excluded and (candidate_bone is None or candidate_bone_proposed):
        flags.append("BONE_BINDING_REVIEW_REQUIRED")
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
    if role == "body.leg":
        return "hinge"
    if role.startswith("body") or role.startswith("accessory"):
        return "rigid"
    return "unknown"


def _candidate_bone(role: str, side: str) -> str | None:
    return region_bone_for_role(role, side)
