"""Canonical browser session for one capture-framed temporary preview v2."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .body_sway_preview_profile_v2 import (
    BASE_ANIMATION_NAME,
    COMBINED_ANIMATION_NAME,
    body_sway_preview_runtime_target_v2,
)
from .spine42_atlas import Spine42Atlas
from .spine42_body_sway_preview_adapter_v2 import Spine42BodySwayPreviewV2


FORMAT = "autospine-temporary-body-sway-preview-session"
FORMAT_VERSION = 2


def build_body_sway_preview_session_v2(
    preview: Spine42BodySwayPreviewV2,
    atlas: Spine42Atlas,
    capture_plan: dict[str, Any],
    *,
    loop: bool,
) -> bytes:
    """Bind exact assets, approved framing, and the v2 capture plan."""

    if type(preview) is not Spine42BodySwayPreviewV2 \
            or type(atlas) is not Spine42Atlas \
            or type(loop) is not bool:
        raise ValueError("Temporary preview v2 session inputs are invalid")
    projection = preview.projection.public_metadata
    world = capture_plan.get("world_viewport")
    if world != projection.get("world_viewport"):
        raise ValueError("Preview v2 session framing identities differ")
    document = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "runtime_target": body_sway_preview_runtime_target_v2(),
        "source": {
            "preview_projection_sha256": projection["projection_sha256"],
            "capture_framing_candidate_sha256":
                projection["capture_framing_candidate_sha256"],
            "capture_framing_decision_sha256":
                projection["capture_framing_decision_sha256"],
            "capture_framing_revision":
                projection["capture_framing_revision"],
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
            "loop": loop,
        },
        "capture_plan": capture_plan,
        "semantics": {
            "mode": "capture-framed-temporary-runtime-preview-v2",
            "capture_framing_human_decision_bound": True,
            "official_runtime_execution_claimed": False,
            "human_visual_review_claimed": False,
            "release_authority": False,
        },
    }
    return json.dumps(
        document, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def require_body_sway_preview_session_v2(
    value: dict[str, Any], *, projection: dict[str, Any],
    capture_plan: dict[str, Any], skeleton_sha256: str,
    atlas_sha256: str, texture_sha256: str,
    texture_size: tuple[int, int], loop: bool,
) -> None:
    """Validate a detached v2 session against exact artifact identities."""

    expected = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "runtime_target": body_sway_preview_runtime_target_v2(),
        "source": {
            "preview_projection_sha256": projection["projection_sha256"],
            "capture_framing_candidate_sha256":
                projection["capture_framing_candidate_sha256"],
            "capture_framing_decision_sha256":
                projection["capture_framing_decision_sha256"],
            "capture_framing_revision":
                projection["capture_framing_revision"],
        },
        "assets": {
            "skeleton": {"path": "skeleton.json", "sha256": skeleton_sha256},
            "atlas": {"path": "skeleton.atlas", "sha256": atlas_sha256},
            "texture": {
                "path": "skeleton.png", "sha256": texture_sha256,
                "size": list(texture_size),
            },
        },
        "animations": {
            "base": BASE_ANIMATION_NAME,
            "combined": COMBINED_ANIMATION_NAME,
            "default": COMBINED_ANIMATION_NAME,
            "loop": loop,
        },
        "capture_plan": capture_plan,
        "semantics": {
            "mode": "capture-framed-temporary-runtime-preview-v2",
            "capture_framing_human_decision_bound": True,
            "official_runtime_execution_claimed": False,
            "human_visual_review_claimed": False,
            "release_authority": False,
        },
    }
    if value != expected:
        raise ValueError("Temporary preview v2 session differs from artifacts")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
