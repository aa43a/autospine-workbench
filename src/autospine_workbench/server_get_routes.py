"""Read-route composition kept outside the bounded HTTP server shell."""

from __future__ import annotations

from .analysis_routes import dispatch_analysis_artifact_get
from .body_sway_visual_review_routes import (
    dispatch_body_sway_visual_review_get,
)
from .mesh_bundle_routes import dispatch_mesh_bundle_get
from . import motion_policy_mutation_routes as policy_mutation
from .motion_policy_preflight_routes import (
    is_motion_policy_preflight_path,
    send_motion_policy_preflight_method_not_allowed,
)
from .motion_policy_review_draft_routes import (
    dispatch_motion_policy_review_draft_get,
    is_motion_policy_review_draft_get_path,
    send_motion_policy_review_draft_method_not_allowed,
)
from .motion_policy_review_package_routes import (
    dispatch_motion_policy_review_package_get,
    is_motion_policy_review_package_path,
    send_motion_policy_review_package_method_not_allowed,
)
from .p10_runtime_capture_routes import (
    dispatch_p10_runtime_capture_get,
    is_p10_runtime_capture_path,
    send_p10_runtime_capture_method_not_allowed,
)
from .p10_visual_review_v2_routes import dispatch_p10_visual_review_v2_get
from .project_routes import dispatch_project_get
from .seam_anchor_review_routes import (
    dispatch_seam_anchor_review_get, is_seam_anchor_review_path,
)
from .split_preview_routes import dispatch_split_preview_get


def dispatch_workbench_api_get(
    parts, store, replay_cache, capture_manager, handler,
) -> bool:
    """Dispatch one API read while preserving route-family method policy."""

    if dispatch_p10_visual_review_v2_get(
        parts, capture_manager, store,
        handler._send_visual_json, handler._send_visual_bytes,
    ):
        return True
    if dispatch_p10_runtime_capture_get(
        parts, capture_manager, handler._send_visual_json,
    ):
        return True
    if is_p10_runtime_capture_path(parts):
        send_p10_runtime_capture_method_not_allowed(parts, handler)
        return True
    if policy_mutation.is_motion_policy_mutation_path(parts):
        policy_mutation.send_motion_policy_mutation_method_not_allowed(
            parts, handler,
        )
        return True
    if is_motion_policy_preflight_path(parts):
        send_motion_policy_preflight_method_not_allowed(handler)
        return True
    if is_seam_anchor_review_path(parts):
        if dispatch_seam_anchor_review_get(
            parts, store, handler._send_visual_json,
            handler._send_visual_bytes, replay_cache,
        ):
            return True
        handler._send_seam_anchor_review_method_not_allowed(parts)
        return True
    if dispatch_body_sway_visual_review_get(
        parts, store, handler._send_visual_json,
        handler._send_visual_bytes,
    ):
        return True
    if dispatch_motion_policy_review_package_get(
        parts, store, handler._send_visual_json, handler.path,
    ):
        return True
    if dispatch_motion_policy_review_draft_get(
        parts, store, handler._send_visual_json, handler.path,
    ):
        return True
    if dispatch_project_get(
        parts, store, handler._send_json, handler._send_file,
    ):
        return True
    if dispatch_mesh_bundle_get(
        parts, store, handler._send_json,
        handler._send_error_json, handler._send_png,
    ):
        return True
    if dispatch_analysis_artifact_get(
        parts, store, handler._send_json, handler._send_error_json,
    ):
        return True
    return dispatch_split_preview_get(
        parts, store, handler._send_json,
        handler._send_error_json, handler._send_file,
    )


__all__ = ["dispatch_workbench_api_get"]
