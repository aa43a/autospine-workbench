"""Pinned identity and resource limits for static seam-anchor inputs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .ik_target_geometry import SOURCE_IDENTITY_FIELDS
from .manifest_artifacts import require_safe_token, require_sha256
from .resolved_project import canonical_sha256


ATTACHMENT_IMAGE_SET_HASH_DOMAIN = (
    "autospine-seam-anchor-attachment-image-set/v1"
)
SEAM_SOURCE_IDENTITY_FIELDS = (
    *SOURCE_IDENTITY_FIELDS, "attachment_image_set_sha256",
)

MAX_LAYER_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_RIG_IR_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_LAYERS = 4_096
MAX_JSON_PREFLIGHT_NODES = 262_144
MAX_JSON_PREFLIGHT_DEPTH = 128
MAX_ATTACHMENTS = 4_096
MAX_RELATION_CANDIDATE_PAIRS = 256
MAX_ATTACHMENT_PNG_BYTES = 72 * 1024 * 1024
MAX_TOTAL_ATTACHMENT_PNG_BYTES = 256 * 1024 * 1024
MAX_ATTACHMENT_PIXELS = 16_777_216
MAX_TOTAL_ATTACHMENT_PIXELS = 67_108_864

_IMAGE_FIELDS = {
    "attachment_id", "image_path", "image_sha256", "width", "height",
}


class SeamAnchorProfileError(ValueError):
    """Raised when static seam identity metadata is not canonical."""


def seam_anchor_resource_limits() -> dict[str, int]:
    """Return a fresh copy of every static-input resource ceiling."""

    return {
        "max_layer_manifest_bytes": MAX_LAYER_MANIFEST_BYTES,
        "max_rig_ir_bytes": MAX_RIG_IR_BYTES,
        "max_manifest_layers": MAX_MANIFEST_LAYERS,
        "max_json_preflight_nodes": MAX_JSON_PREFLIGHT_NODES,
        "max_json_preflight_depth": MAX_JSON_PREFLIGHT_DEPTH,
        "max_attachments": MAX_ATTACHMENTS,
        "max_relation_candidate_pairs": MAX_RELATION_CANDIDATE_PAIRS,
        "max_attachment_png_bytes": MAX_ATTACHMENT_PNG_BYTES,
        "max_total_attachment_png_bytes": MAX_TOTAL_ATTACHMENT_PNG_BYTES,
        "max_attachment_pixels": MAX_ATTACHMENT_PIXELS,
        "max_total_attachment_pixels": MAX_TOTAL_ATTACHMENT_PIXELS,
    }


def attachment_image_set_sha256(
    images: Sequence[Mapping[str, Any]],
) -> str:
    """Hash a canonical, order-independent attachment image inventory."""

    try:
        if not isinstance(images, Sequence) or isinstance(
            images, (str, bytes, bytearray)
        ) or len(images) > MAX_ATTACHMENTS:
            raise SeamAnchorProfileError(
                "Attachment image identity inventory must be an array"
            )
        rows, ids, paths, total_pixels = [], set(), set(), 0
        for raw in images:
            if not isinstance(raw, Mapping) or set(raw) != _IMAGE_FIELDS:
                raise SeamAnchorProfileError(
                    "Attachment image identity fields are invalid"
                )
            identifier = require_safe_token(
                raw.get("attachment_id"), "Attachment id"
            )
            path = raw.get("image_path")
            parts = path.split("/") if isinstance(path, str) else []
            if len(parts) != 2 or parts[0] != "layers" \
                    or not parts[1].endswith(".png") or "\\" in path:
                raise SeamAnchorProfileError(
                    "Attachment image identity path is invalid"
                )
            require_safe_token(parts[1][:-4], "Attachment image layer")
            digest = require_sha256(
                raw.get("image_sha256"), "Attachment image"
            )
            width, height = raw.get("width"), raw.get("height")
            if type(width) is not int or type(height) is not int \
                    or width < 1 or height < 1:
                raise SeamAnchorProfileError(
                    "Attachment image identity dimensions are invalid"
                )
            total_pixels += width * height
            if width * height > MAX_ATTACHMENT_PIXELS \
                    or total_pixels > MAX_TOTAL_ATTACHMENT_PIXELS:
                raise SeamAnchorProfileError(
                    "Attachment image identity pixel limit exceeded"
                )
            if identifier.casefold() in ids or path.casefold() in paths:
                raise SeamAnchorProfileError(
                    "Attachment image identities are duplicated"
                )
            ids.add(identifier.casefold())
            paths.add(path.casefold())
            rows.append({
                "attachment_id": identifier, "image_path": path,
                "image_sha256": digest, "width": width, "height": height,
            })
        rows.sort(key=lambda row: row["attachment_id"])
        return canonical_sha256({
            "domain": ATTACHMENT_IMAGE_SET_HASH_DOMAIN,
            "images": rows,
        })
    except SeamAnchorProfileError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise SeamAnchorProfileError(
            f"Attachment image set identity is invalid: {exc}"
        ) from exc
