"""Exact P3 and original-image source boundary for static seam anchors."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .ik_target_geometry import SOURCE_IDENTITY_FIELDS
from .manifest_artifacts import LayerManifestError, validate_raster_geometry
from .mesh_bundle_admission import MeshBundleAdmissionError, require_exact_mesh_bundle
from .mesh_bundle_integrity import VerifiedMeshBundle
from .mesh_source_from_bundle import (
    VerifiedMeshBundleSourceError,
    verified_mesh_source_from_bundle,
)
from .mesh_source_images import AttachmentImageBudget
from .resolved_project import canonical_sha256
from . import seam_anchor_profile as profile


_CANVAS_AXES = {
    "origin": "top_left", "x_axis": "right", "y_axis": "down",
    "units": "pixel",
}


class SeamAnchorSourceError(ValueError):
    """Raised when an exact static P3 source cannot be admitted."""


@dataclass(frozen=True, slots=True)
class AdmittedSeamAnchorSource:
    """Internal frozen P3/image replay result."""

    rig_json: str = field(repr=False)
    image_items: tuple[tuple[str, str, str, int, int, bytes], ...] = field(
        repr=False
    )
    image_rows_json: str = field(repr=False)
    source_json: str = field(repr=False)
    attachment_image_set_sha256: str

    @property
    def image_rows(self) -> list[dict[str, Any]]:
        return json.loads(self.image_rows_json)


def admit_seam_anchor_source(
    manifest: Mapping[str, Any],
    canvas: tuple[int, int],
    layers: Mapping[str, Mapping[str, Any]],
    mesh_bundle: VerifiedMeshBundle,
) -> AdmittedSeamAnchorSource:
    """Replay P3 and its source adapter, then bind every original PNG."""

    try:
        rig = require_exact_mesh_bundle(mesh_bundle)
        rig_json = _snapshot_rig(rig)
        attachments = _attachment_index(rig)
        source_images = verified_mesh_source_from_bundle(
            mesh_bundle, image_budget=_image_budget()
        )
        if source_images.rig != rig:
            raise SeamAnchorSourceError(
                "P3 source adapter RigIR differs from admitted content"
            )
        image_items, image_rows = _freeze_images(source_images.images)
        _cross_bind(
            manifest, canvas, layers, rig, attachments, image_rows,
            mesh_bundle,
        )
        image_set_sha = profile.attachment_image_set_sha256(image_rows)
        source = {
            field: getattr(mesh_bundle, field)
            for field in SOURCE_IDENTITY_FIELDS
        }
        source["attachment_image_set_sha256"] = image_set_sha
        return AdmittedSeamAnchorSource(
            rig_json, image_items, _canonical(image_rows),
            _canonical(source), image_set_sha,
        )
    except SeamAnchorSourceError:
        raise
    except _FAILURES as exc:
        raise SeamAnchorSourceError(
            f"Static seam source admission failed: {exc}"
        ) from exc


def _snapshot_rig(value: Mapping[str, Any]) -> str:
    text = _canonical(dict(value))
    if len(text.encode("utf-8")) > profile.MAX_RIG_IR_BYTES:
        raise SeamAnchorSourceError("P3 RigIR resource limit exceeded")
    return text


def _image_budget() -> AttachmentImageBudget:
    return AttachmentImageBudget(
        max_images=profile.MAX_ATTACHMENTS,
        max_image_bytes=profile.MAX_ATTACHMENT_PNG_BYTES,
        max_total_bytes=profile.MAX_TOTAL_ATTACHMENT_PNG_BYTES,
        max_image_pixels=profile.MAX_ATTACHMENT_PIXELS,
        max_total_pixels=profile.MAX_TOTAL_ATTACHMENT_PIXELS,
    )


def _attachment_index(rig):
    rows = rig.get("attachments")
    if not isinstance(rows, list) or len(rows) > profile.MAX_ATTACHMENTS:
        raise SeamAnchorSourceError("P3 attachment resource limit exceeded")
    result = {}
    for row in rows:
        if not isinstance(row, Mapping) or row.get("id") in result:
            raise SeamAnchorSourceError("P3 attachment inventory is invalid")
        result[row["id"]] = row
    return result


def _freeze_images(images):
    if not isinstance(images, Sequence) or len(images) > profile.MAX_ATTACHMENTS:
        raise SeamAnchorSourceError("Attachment image resource limit exceeded")
    items, rows, total_bytes, total_pixels = [], [], 0, 0
    for image in images:
        raw = image.png_bytes
        pixels = image.width * image.height
        total_bytes += len(raw)
        total_pixels += pixels
        if len(raw) > profile.MAX_ATTACHMENT_PNG_BYTES \
                or total_bytes > profile.MAX_TOTAL_ATTACHMENT_PNG_BYTES \
                or pixels > profile.MAX_ATTACHMENT_PIXELS \
                or total_pixels > profile.MAX_TOTAL_ATTACHMENT_PIXELS:
            raise SeamAnchorSourceError(
                "Attachment image resource limit exceeded"
            )
        if hashlib.sha256(raw).hexdigest() != image.image_sha256:
            raise SeamAnchorSourceError(
                "Attachment image bytes differ from identity"
            )
        row = {
            "attachment_id": image.attachment_id,
            "image_path": image.image_path,
            "image_sha256": image.image_sha256,
            "width": image.width,
            "height": image.height,
        }
        rows.append(row)
        items.append((
            image.attachment_id, image.image_path, image.image_sha256,
            image.width, image.height, bytes(raw),
        ))
    return tuple(items), rows


def _cross_bind(manifest, canvas, layers, rig, attachments, images, bundle):
    if manifest["project_id"] != bundle.project_id \
            or canonical_sha256(manifest) != bundle.layer_manifest_sha256:
        raise SeamAnchorSourceError("Layer Manifest and P3 identity differ")
    expected_canvas = {
        "width": canvas[0], "height": canvas[1], **_CANVAS_AXES,
    }
    if rig.get("canvas") != expected_canvas or len(images) != len(attachments):
        raise SeamAnchorSourceError(
            "Layer Manifest and P3 static geometry differ"
        )
    by_image = {row["attachment_id"]: row for row in images}
    if set(by_image) != set(attachments):
        raise SeamAnchorSourceError(
            "Attachment image inventory differs from P3"
        )
    for identifier, attachment in attachments.items():
        source_ids = attachment.get("source_layer_ids")
        image = by_image[identifier]
        if not isinstance(source_ids, list) or len(source_ids) != 1 \
                or source_ids[0] not in layers:
            raise SeamAnchorSourceError("P3 attachment source layer is absent")
        raster = layers[source_ids[0]]["raster"]
        if raster["artifact_path"] != image["image_path"] \
                or raster["sha256"] != image["image_sha256"] \
                or attachment.get("canvas_offset_xy") != raster["canvas_offset_xy"]:
            raise SeamAnchorSourceError(
                "Manifest raster and attachment image differ"
            )
        validate_raster_geometry(
            raster, (image["width"], image["height"]), canvas,
            layer_id=source_ids[0],
        )


def _canonical(value):
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )


_FAILURES = (
    AttributeError, KeyError, LayerManifestError, MeshBundleAdmissionError,
    OverflowError, RecursionError, TypeError, UnicodeError, ValueError,
    VerifiedMeshBundleSourceError,
)
