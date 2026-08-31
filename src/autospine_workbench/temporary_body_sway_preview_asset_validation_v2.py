"""Strict byte validation for capture-framed preview v2 artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import hashlib
import json
from typing import Any

from .body_sway_preview_page import body_sway_preview_player_html
from .body_sway_preview_profile import body_sway_preview_adapter_profile
from .body_sway_preview_projection import body_sway_preview_setup_sha256
from .body_sway_preview_projection_v2 import body_sway_preview_setup_sha256_v2
from .body_sway_preview_session_v2 import require_body_sway_preview_session_v2
from .png_rgba import RgbaPngError, decode_rgba_png
from .resolved_project import canonical_sha256
from .safe_input_files import SafeInputFileError, strict_json_object
from .spine42_body_sway_preview_adapter_v2 import (
    body_sway_preview_skeleton_hash_v2,
)
from .spine42_contract import Spine42ContractError
from .spine42_export_validation import (
    Spine42ExportValidationError,
    require_spine42_atlas_inventory,
)
from .spine42_json_adapter import require_projected_spine42_document
from .temporary_body_sway_preview_artifacts import ARTIFACT_PATHS
from .temporary_body_sway_preview_inventory_v2 import (
    TemporaryBodySwayPreviewInventoryV2Error,
    require_temporary_body_sway_preview_inventory_v2,
)
from .temporary_body_sway_preview_skeleton_validation import (
    TemporaryBodySwayPreviewSkeletonError,
    require_temporary_body_sway_preview_skeleton,
)
from .temporary_body_sway_preview_timeline_validation_v2 import (
    TemporaryBodySwayPreviewTimelineV2Error,
    require_temporary_body_sway_preview_timeline_v2,
)


class TemporaryBodySwayPreviewAssetValidationV2Error(ValueError):
    """Raised when v2 preview bytes differ from their framed manifest."""


def require_temporary_body_sway_preview_artifacts_v2(
    inventory: Mapping[str, Any], artifact_bytes: Mapping[str, bytes], *,
    project_id: str, clip_id: str, source: Mapping[str, Any],
    selection: Mapping[str, Any], timing: Mapping[str, Any],
    runtime_target: Mapping[str, Any], projection: Mapping[str, Any],
    capture_plan: Mapping[str, Any],
) -> dict[str, int]:
    """Validate exact files, dynamic setup, timelines, atlas, PNG, session."""

    try:
        rows = require_temporary_body_sway_preview_inventory_v2(inventory)
        if not isinstance(artifact_bytes, Mapping) \
                or tuple(sorted(artifact_bytes)) != ARTIFACT_PATHS:
            raise TemporaryBodySwayPreviewAssetValidationV2Error(
                "Temporary preview v2 artifact bytes are incomplete"
            )
        values = _require_declared_bytes(rows, artifact_bytes)
        if values["runtime/player.html"] != body_sway_preview_player_html():
            raise TemporaryBodySwayPreviewAssetValidationV2Error(
                "Temporary preview v2 player is not the pinned page"
            )
        texture = decode_rgba_png(
            values["runtime/skeleton.png"], source_name="skeleton.png"
        )
        skeleton = _canonical_json(
            values["runtime/skeleton.json"], "preview v2 skeleton"
        )
        counts = _require_skeleton(
            skeleton, capture_plan, source, projection
        )
        require_projected_spine42_document(skeleton)
        require_temporary_body_sway_preview_timeline_v2(
            skeleton, projection, timing, source, selection,
            project_id=project_id, clip_id=clip_id,
        )
        atlas_width, atlas_height, atlas_regions = (
            require_spine42_atlas_inventory(values["runtime/skeleton.atlas"])
        )
        if (atlas_width, atlas_height) != (texture.width, texture.height) \
                or set(atlas_regions) != counts["attachment_ids"]:
            raise TemporaryBodySwayPreviewAssetValidationV2Error(
                "Preview v2 atlas differs from skeleton or texture"
            )
        for name, size in counts["region_sizes"].items():
            if atlas_regions[name][2:] != size:
                raise TemporaryBodySwayPreviewAssetValidationV2Error(
                    f"Preview v2 atlas region size differs: {name}"
                )
        session = _canonical_json(
            values["runtime/session.json"], "preview v2 session"
        )
        require_body_sway_preview_session_v2(
            session, projection=dict(projection),
            capture_plan=dict(capture_plan),
            skeleton_sha256=_sha(values["runtime/skeleton.json"]),
            atlas_sha256=_sha(values["runtime/skeleton.atlas"]),
            texture_sha256=_sha(values["runtime/skeleton.png"]),
            texture_size=(texture.width, texture.height), loop=timing["loop"],
        )
        return {
            "artifact_total_bytes": sum(map(len, values.values())),
            "bone_count": counts["bone_count"],
            "slot_count": counts["slot_count"],
            "attachment_count": len(counts["attachment_ids"]),
            "region_attachment_count": counts["region_attachment_count"],
            "mesh_attachment_count": counts["mesh_attachment_count"],
            "atlas_width": texture.width,
            "atlas_height": texture.height,
        }
    except TemporaryBodySwayPreviewAssetValidationV2Error:
        raise
    except (
        RgbaPngError, SafeInputFileError, Spine42ContractError,
        Spine42ExportValidationError, TemporaryBodySwayPreviewInventoryV2Error,
        TemporaryBodySwayPreviewSkeletonError,
        TemporaryBodySwayPreviewTimelineV2Error,
        AttributeError, KeyError, OverflowError, RecursionError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise TemporaryBodySwayPreviewAssetValidationV2Error(
            f"Temporary preview v2 artifact validation failed: {exc}"
        ) from exc


def _require_declared_bytes(rows, artifacts):
    values = {}
    for row in rows:
        path, raw = row["path"], artifacts[row["path"]]
        if type(raw) is not bytes or len(raw) != row["size_bytes"] \
                or _sha(raw) != row["sha256"]:
            raise TemporaryBodySwayPreviewAssetValidationV2Error(
                f"Temporary preview v2 artifact bytes differ: {path}"
            )
        values[path] = raw
    return values


def _require_skeleton(skeleton, capture, source, projection):
    metadata = skeleton.get("skeleton")
    world = projection["world_viewport"]
    if not isinstance(metadata, Mapping) \
            or any(metadata.get(field) != world[field]
                   for field in ("x", "y", "width", "height")) \
            or capture["world_viewport"] != world \
            or body_sway_preview_setup_sha256_v2(skeleton) \
            != projection["setup_sha256"]:
        raise TemporaryBodySwayPreviewAssetValidationV2Error(
            "Preview v2 skeleton bounds differ from approved framing"
        )
    expected_hash = body_sway_preview_skeleton_hash_v2(
        rig_sha256=source["p3"]["rig_sha256"],
        target_profile_sha256=source["p5"]["target_profile_sha256"],
        motion_instance_v2_sha256=source["p9"]["motion_instance_v2_sha256"],
        body_sway_probe_report_sha256=
            source["body_sway_probe_report_sha256"],
        preview_projection_sha256=projection["projection_sha256"],
        capture_framing_candidate_sha256=
            source["capture_framing_candidate_sha256"],
        capture_framing_decision_sha256=
            source["capture_framing_decision_sha256"],
        world_viewport=world,
    )
    if metadata.get("hash") != expected_hash:
        raise TemporaryBodySwayPreviewAssetValidationV2Error(
            "Preview v2 skeleton hash differs from exact sources"
        )
    legacy = deepcopy(skeleton)
    legacy_projection = _legacy_projection(projection, legacy)
    legacy["skeleton"]["hash"] = canonical_sha256({
        "adapter_profile": body_sway_preview_adapter_profile(),
        "rig_sha256": source["p3"]["rig_sha256"],
        "target_profile_sha256": source["p5"]["target_profile_sha256"],
        "motion_instance_v2_sha256":
            source["p9"]["motion_instance_v2_sha256"],
        "body_sway_probe_report_sha256":
            source["body_sway_probe_report_sha256"],
        "preview_projection_sha256": legacy_projection["projection_sha256"],
    })
    return require_temporary_body_sway_preview_skeleton(
        legacy, capture, source, legacy_projection,
    )


def _legacy_projection(projection, skeleton):
    fields = {
        "projection_sha256", "probe_tick_schedule_sha256",
        "probe_sample_stream_sha256", "base_motion_instance_v2_sha256",
        "base_animation_sha256", "setup_sha256", "rotation_timeline_sha256",
        "sample_ticks", "rotation_bone_ids", "sample_count",
        "rotation_track_count", "rotation_key_count", "sampling",
        "rotation_interpolation", "root_translation", "markers", "draw_order",
        "animation_names",
    }
    value = {field: projection[field] for field in fields}
    value["projection_sha256"] = projection["legacy_projection_sha256"]
    value["setup_sha256"] = body_sway_preview_setup_sha256(skeleton)
    return value


def _canonical_json(raw: bytes, label: str) -> dict[str, Any]:
    value = strict_json_object(raw, label)
    if _canonical(value) != raw:
        raise TemporaryBodySwayPreviewAssetValidationV2Error(
            f"Temporary {label} bytes are not canonical JSON"
        )
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
