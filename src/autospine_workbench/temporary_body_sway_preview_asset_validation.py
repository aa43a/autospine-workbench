"""Strict byte-level validation for a temporary preview's five artifacts."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from typing import Any

from .body_sway_preview_page import body_sway_preview_player_html
from .body_sway_preview_profile import BASE_ANIMATION_NAME, COMBINED_ANIMATION_NAME
from .png_rgba import RgbaPngError, decode_rgba_png
from .safe_input_files import SafeInputFileError, strict_json_object
from .spine42_contract import Spine42ContractError
from .spine42_export_validation import (
    Spine42ExportValidationError,
    require_spine42_atlas_inventory,
)
from .spine42_json_adapter import require_projected_spine42_document
from .temporary_body_sway_preview_artifacts import ARTIFACT_PATHS
from .temporary_body_sway_preview_inventory import (
    TemporaryBodySwayPreviewInventoryError,
    require_temporary_body_sway_preview_inventory,
)
from .temporary_body_sway_preview_skeleton_validation import (
    TemporaryBodySwayPreviewSkeletonError,
    require_temporary_body_sway_preview_skeleton,
)
from .temporary_body_sway_preview_timeline_validation import (
    TemporaryBodySwayPreviewTimelineError,
    require_temporary_body_sway_preview_timeline,
)


class TemporaryBodySwayPreviewAssetValidationError(ValueError):
    """Raised when preview bytes differ from the manifest or fixed package."""


def require_temporary_body_sway_preview_artifacts(
    inventory: Mapping[str, Any],
    artifact_bytes: Mapping[str, bytes],
    *,
    project_id: str,
    clip_id: str,
    source: Mapping[str, Any],
    selection: Mapping[str, Any],
    timing: Mapping[str, Any],
    runtime_target: Mapping[str, Any],
    projection: Mapping[str, Any],
    capture_plan: Mapping[str, Any],
) -> dict[str, int]:
    """Validate hashes, exact support files, Spine inventory, atlas, and PNG."""

    try:
        rows = require_temporary_body_sway_preview_inventory(inventory)
        if not isinstance(artifact_bytes, Mapping) \
                or tuple(sorted(artifact_bytes)) != ARTIFACT_PATHS:
            raise TemporaryBodySwayPreviewAssetValidationError(
                "Temporary preview artifact bytes are incomplete"
            )
        values: dict[str, bytes] = {}
        for row in rows:
            path = row["path"]
            raw = artifact_bytes[path]
            if type(raw) is not bytes or len(raw) != row["size_bytes"] \
                    or _sha(raw) != row["sha256"]:
                raise TemporaryBodySwayPreviewAssetValidationError(
                    f"Temporary preview artifact bytes differ: {path}"
                )
            values[path] = raw
        if values["runtime/player.html"] != body_sway_preview_player_html():
            raise TemporaryBodySwayPreviewAssetValidationError(
                "Temporary preview player HTML is not the pinned page"
            )
        texture = decode_rgba_png(
            values["runtime/skeleton.png"], source_name="skeleton.png"
        )
        skeleton = _canonical_json(
            values["runtime/skeleton.json"], "preview skeleton"
        )
        require_projected_spine42_document(skeleton)
        counts = require_temporary_body_sway_preview_skeleton(
            skeleton, capture_plan, source, projection
        )
        require_temporary_body_sway_preview_timeline(
            skeleton, projection, timing, source, selection,
            project_id=project_id, clip_id=clip_id,
        )
        atlas_width, atlas_height, atlas_regions = (
            require_spine42_atlas_inventory(
                values["runtime/skeleton.atlas"]
            )
        )
        if (atlas_width, atlas_height) != (texture.width, texture.height) \
                or set(atlas_regions) != counts["attachment_ids"]:
            raise TemporaryBodySwayPreviewAssetValidationError(
                "Temporary preview atlas differs from skeleton or texture"
            )
        for name, size in counts["region_sizes"].items():
            if atlas_regions[name][2:] != size:
                raise TemporaryBodySwayPreviewAssetValidationError(
                    f"Temporary preview region size differs: {name}"
                )
        session = _canonical_json(
            values["runtime/session.json"], "preview session"
        )
        expected_session = _session(
            runtime_target, projection, capture_plan, rows,
            texture.width, texture.height, timing["loop"],
        )
        if session != expected_session:
            raise TemporaryBodySwayPreviewAssetValidationError(
                "Temporary preview session differs from exact artifacts"
            )
        return {
            "artifact_total_bytes": sum(len(raw) for raw in values.values()),
            "bone_count": counts["bone_count"],
            "slot_count": counts["slot_count"],
            "attachment_count": len(counts["attachment_ids"]),
            "region_attachment_count": counts["region_attachment_count"],
            "mesh_attachment_count": counts["mesh_attachment_count"],
            "atlas_width": texture.width,
            "atlas_height": texture.height,
        }
    except TemporaryBodySwayPreviewAssetValidationError:
        raise
    except (
        RgbaPngError, SafeInputFileError, Spine42ContractError,
        Spine42ExportValidationError, TemporaryBodySwayPreviewTimelineError,
        TemporaryBodySwayPreviewInventoryError,
        TemporaryBodySwayPreviewSkeletonError,
        KeyError, OverflowError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise TemporaryBodySwayPreviewAssetValidationError(
            f"Temporary preview artifact validation failed: {exc}"
        ) from exc


def _canonical_json(raw: bytes, label: str) -> dict[str, Any]:
    value = strict_json_object(raw, label)
    if _canonical(value) != raw:
        raise TemporaryBodySwayPreviewAssetValidationError(
            f"Temporary {label} bytes are not canonical JSON"
        )
    return value


def _session(runtime, projection, capture, rows, width, height, loop):
    identities = {row["role"]: row["sha256"] for row in rows}
    return {
        "format": "autospine-temporary-body-sway-preview-session",
        "format_version": 1,
        "runtime_target": dict(runtime),
        "source": {
            "preview_projection_sha256": projection["projection_sha256"],
        },
        "assets": {
            "skeleton": {
                "path": "skeleton.json",
                "sha256": identities["spine-skeleton"],
            },
            "atlas": {
                "path": "skeleton.atlas",
                "sha256": identities["spine-atlas"],
            },
            "texture": {
                "path": "skeleton.png",
                "sha256": identities["spine-texture"],
                "size": [width, height],
            },
        },
        "animations": {
            "base": BASE_ANIMATION_NAME,
            "combined": COMBINED_ANIMATION_NAME,
            "default": COMBINED_ANIMATION_NAME,
            "loop": loop,
        },
        "capture_plan": dict(capture),
        "semantics": {
            "mode": "temporary-runtime-preview",
            "official_runtime_execution_claimed": False,
            "human_review_claimed": False,
            "release_authority": False,
        },
    }


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
