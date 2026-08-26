"""Canonical browser session for one in-memory temporary preview package."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .body_sway_preview_profile import (
    BASE_ANIMATION_NAME,
    COMBINED_ANIMATION_NAME,
    body_sway_preview_runtime_target,
)
from .spine42_atlas import Spine42Atlas
from .spine42_body_sway_preview_adapter import Spine42BodySwayPreview


def build_body_sway_preview_session(
    preview: Spine42BodySwayPreview,
    atlas: Spine42Atlas,
    capture_plan: dict[str, Any],
) -> bytes:
    """Bind exact runtime assets and plan without claiming runtime execution."""

    document = {
        "format": "autospine-temporary-body-sway-preview-session",
        "format_version": 1,
        "runtime_target": body_sway_preview_runtime_target(),
        "source": {
            "preview_projection_sha256": preview.projection.sha256,
        },
        "assets": {
            "skeleton": {
                "path": "skeleton.json",
                "sha256": preview.skeleton_sha256,
            },
            "atlas": {
                "path": "skeleton.atlas",
                "sha256": _sha(atlas.atlas_bytes),
            },
            "texture": {
                "path": "skeleton.png",
                "sha256": _sha(atlas.png_bytes),
                "size": [atlas.width, atlas.height],
            },
        },
        "animations": {
            "base": BASE_ANIMATION_NAME,
            "combined": COMBINED_ANIMATION_NAME,
            "default": COMBINED_ANIMATION_NAME,
            "loop": True,
        },
        "capture_plan": capture_plan,
        "semantics": {
            "mode": "temporary-runtime-preview",
            "official_runtime_execution_claimed": False,
            "human_review_claimed": False,
            "release_authority": False,
        },
    }
    return json.dumps(
        document, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
