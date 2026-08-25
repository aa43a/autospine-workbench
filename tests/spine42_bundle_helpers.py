"""Shared exact fixtures for Spine 4.2 export bundle tests."""

from __future__ import annotations

import hashlib

from autospine_workbench.png_rgba import RgbaImage, encode_rgba_png
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.spine42_atlas import build_spine42_atlas
from autospine_workbench.spine42_json_adapter import build_spine42_json
from tests.test_spine42_json_adapter import motion_pair, rig_fixture


def bundle_inputs(*, motion: bool = False) -> dict:
    rig = rig_fixture()
    first = encode_rgba_png(RgbaImage(20, 30, bytes(20 * 30 * 4)))
    second = encode_rgba_png(RgbaImage(
        20, 40, bytes((10, 20, 30, 255)) * (20 * 40)
    ))
    sources = {"face-image": first, "leg-mesh": second}
    atlas = build_spine42_atlas(sources, page_name="skeleton.png")
    p5 = None
    if motion:
        target, instance = motion_pair(rig)
        document = build_spine42_json(
            rig, motion_instance=instance, target_profile=target
        )
        p5 = {
            "target_profile_sha256": canonical_sha256(target),
            "motion_instance_sha256": canonical_sha256(instance),
            "bundle_sha256": "5" * 64,
            "clip_id": instance["clip_id"],
        }
    else:
        document = build_spine42_json(rig)
    return {
        "project_id": "sample-project",
        "p3_source": {
            "rig_sha256": canonical_sha256(rig),
            "bundle_sha256": "3" * 64,
        },
        "skeleton_json": document,
        "atlas_bytes": atlas.atlas_bytes,
        "png_bytes": atlas.png_bytes,
        "source_image_sha256s": {
            name: hashlib.sha256(data).hexdigest()
            for name, data in sources.items()
        },
        "p5_source": p5,
    }


def build_args(values: dict) -> tuple:
    return (
        values["project_id"], values["p3_source"], values["skeleton_json"],
        values["atlas_bytes"], values["png_bytes"],
        values["source_image_sha256s"],
    )
