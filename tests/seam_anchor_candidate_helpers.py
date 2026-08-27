"""Small admitted-value fixture for pure static seam candidate tests."""

from __future__ import annotations

import hashlib
import json

from autospine_workbench.png_rgba import RgbaImage, encode_rgba_png
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.seam_anchor_inputs import SeamAnchorInputs
from autospine_workbench.seam_anchor_profile import (
    attachment_image_set_sha256,
)


_SPECS = (
    ("torso", "body.torso", "center", (20, 10), (20, 20)),
    ("pelvis", "body.pelvis", "bilateral", (20, 27), (20, 10)),
    ("arm.left", "body.arm.upper", "left", (10, 15), (15, 6)),
    ("arm.right", "body.arm.upper", "right", (35, 15), (15, 6)),
    ("leg.left", "body.leg", "left", (21, 33), (6, 16)),
    ("leg.right", "body.leg", "right", (33, 33), (6, 16)),
    ("foot.left", "body.foot", "left", (18, 45), (10, 6)),
    ("foot.right", "body.foot", "right", (32, 45), (10, 6)),
)


def seam_inputs(*, mesh_id: str | None = None,
                gap_arm_left: bool = False) -> SeamAnchorInputs:
    specs = list(_SPECS)
    if gap_arm_left:
        specs[2] = (*specs[2][:3], (0, 15), specs[2][4])
    layers = [{
        "layer_id": identifier,
        "source": {"visible": True},
        "semantic": {"canonical_role": role, "side": side},
    } for identifier, role, side, _, _ in specs]
    manifest = {
        "format": "autospine-layer-manifest", "format_version": 1,
        "layers": layers, "qa": {"status": "passed"},
    }
    attachments, image_items, image_rows = [], [], []
    for identifier, _, _, offset, size in specs:
        width, height = size
        kind = "mesh" if identifier == mesh_id else "region"
        attachment = {
            "id": identifier, "slot": identifier, "type": kind,
            "source_layer_ids": [identifier],
            "canvas_offset_xy": list(offset), "size": list(size),
        }
        if kind == "mesh":
            attachment.update({
                "vertices": [[0, 0], [width, 0], [0, height],
                             [width, height]],
                "triangles": [0, 1, 2, 1, 3, 2],
            })
        attachments.append(attachment)
        raw = opaque_png(width, height)
        digest = hashlib.sha256(raw).hexdigest()
        path = f"layers/{identifier}.png"
        image_items.append((identifier, path, digest, width, height, raw))
        image_rows.append({
            "attachment_id": identifier, "image_path": path,
            "image_sha256": digest, "width": width, "height": height,
        })
    manifest_sha = canonical_sha256(manifest)
    rig = {
        "format": "autospine-rig-ir", "format_version": 1,
        "source": {"layer_manifest_sha256": manifest_sha},
        "slots": [{"id": row[0], "setup_attachment": row[0]}
                  for row in specs],
        "attachments": attachments,
        "skins": {"default": {row[0]: [row[0]] for row in specs}},
        "qa": {"status": "passed"},
    }
    source = {
        "base_rig_sha256": "1" * 64,
        "base_bundle_sha256": "2" * 64,
        "layer_manifest_sha256": manifest_sha,
        "resolved_project_sha256": "3" * 64,
        "rig_sha256": "4" * 64,
        "run_sha256": "5" * 64,
        "probes_sha256": "6" * 64,
        "visuals_sha256": "7" * 64,
        "bundle_sha256": "8" * 64,
        "attachment_image_set_sha256": attachment_image_set_sha256(
            image_rows
        ),
    }
    canonical = lambda value: json.dumps(
        value, sort_keys=True, separators=(",", ":")
    )
    return SeamAnchorInputs(
        "seam-fixture", manifest_sha,
        source["attachment_image_set_sha256"], canonical(manifest),
        canonical(rig), tuple(image_items), canonical(source),
    )


def opaque_png(width: int, height: int) -> bytes:
    return encode_rgba_png(RgbaImage(
        width, height, bytes([255, 255, 255, 255]) * width * height
    ))
