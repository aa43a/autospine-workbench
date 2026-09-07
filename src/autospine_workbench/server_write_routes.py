"""Write-route composition kept outside the bounded HTTP server shell."""

from __future__ import annotations

from .body_sway_visual_review_routes import (
    dispatch_body_sway_visual_review_put,
)
from . import motion_policy_mutation_routes as policy_mutation
from .motion_policy_preflight_routes import (
    dispatch_motion_policy_preflight_post,
    is_motion_policy_preflight_path,
    send_motion_policy_preflight_method_not_allowed,
)
from .motion_policy_review_draft_routes import (
    is_motion_policy_review_draft_get_path,
    send_motion_policy_review_draft_method_not_allowed,
)
from .motion_policy_review_package_routes import (
    is_motion_policy_review_package_path,
    send_motion_policy_review_package_method_not_allowed,
)
from .p10_dynamic_seam_v2_routes import (
    dispatch_p10_dynamic_seam_v2_post,
    is_p10_dynamic_seam_v2_path,
    send_p10_dynamic_seam_v2_method_not_allowed,
)
from .p10_motion_instance_v3_v2_routes import (
    dispatch_p10_motion_instance_v3_v2_post,
    is_p10_motion_instance_v3_v2_path,
    send_p10_motion_instance_v3_v2_method_not_allowed,
)
from .p10_spine42_v3_v2_routes import (
    dispatch_p10_spine42_v3_v2_post,
    is_p10_spine42_v3_v2_path,
    send_p10_spine42_v3_v2_method_not_allowed,
)
from .p10_spine42_v3_runtime_routes_v2 import (
    dispatch_p10_spine42_v3_runtime_v2_post,
    is_p10_spine42_v3_runtime_v2_path,
    send_p10_spine42_v3_runtime_v2_method_not_allowed,
)
from .p10_runtime_capture_routes import (
    dispatch_p10_runtime_capture_post,
    is_p10_runtime_capture_path,
    send_p10_runtime_capture_method_not_allowed,
)
from .p10_safety_analysis_v2_routes import (
    dispatch_p10_safety_analysis_v2_post,
    is_p10_safety_analysis_v2_path,
    send_p10_safety_analysis_v2_method_not_allowed,
)
from .p10_visual_review_v2_routes import (
    dispatch_p10_visual_review_v2_put,
)
from .seam_anchor_review_routes import (
    dispatch_seam_anchor_review_post,
    is_seam_anchor_review_path,
)


def dispatch_workbench_api_put(
    parts, store, capture_manager, handler,
) -> bool:
    """Dispatch PUT-only families and their exact method policies."""

    if policy_mutation.is_motion_policy_mutation_path(parts):
        policy_mutation.send_motion_policy_mutation_method_not_allowed(
            parts, handler,
        )
        return True
    if is_motion_policy_preflight_path(parts):
        send_motion_policy_preflight_method_not_allowed(handler)
        return True
    if is_motion_policy_review_package_path(parts):
        send_motion_policy_review_package_method_not_allowed(handler)
        return True
    if is_motion_policy_review_draft_get_path(parts):
        send_motion_policy_review_draft_method_not_allowed(handler)
        return True
    if is_p10_spine42_v3_runtime_v2_path(parts):
        send_p10_spine42_v3_runtime_v2_method_not_allowed(parts, handler)
        return True
    if is_p10_spine42_v3_v2_path(parts):
        send_p10_spine42_v3_v2_method_not_allowed(parts, handler)
        return True
    if is_p10_motion_instance_v3_v2_path(parts):
        send_p10_motion_instance_v3_v2_method_not_allowed(parts, handler)
        return True
    if is_p10_dynamic_seam_v2_path(parts):
        send_p10_dynamic_seam_v2_method_not_allowed(parts, handler)
        return True
    if is_p10_safety_analysis_v2_path(parts):
        send_p10_safety_analysis_v2_method_not_allowed(parts, handler)
        return True
    if dispatch_p10_visual_review_v2_put(
        parts, capture_manager, store, handler,
        handler._send_visual_json,
    ):
        return True
    if is_p10_runtime_capture_path(parts):
        send_p10_runtime_capture_method_not_allowed(parts, handler)
        return True
    if dispatch_body_sway_visual_review_put(
        parts, store, handler, handler._send_visual_json,
    ):
        return True
    if is_seam_anchor_review_path(parts):
        handler._send_seam_anchor_review_method_not_allowed(parts)
        return True
    if handler._mesh_bundle_path(parts):
        handler._send_method_not_allowed(read_only=True)
        return True
    return False


def dispatch_workbench_api_post(
    parts, store, replay_cache, capture_manager,
    safety_analysis_v2_manager, dynamic_seam_v2_manager,
    motion_instance_v3_v2_manager, spine42_v3_v2_manager,
    spine42_v3_runtime_v2_manager, handler,
) -> bool:
    """Dispatch mutation families in most-specific-first order."""

    if dispatch_p10_spine42_v3_runtime_v2_post(
        parts, handler, spine42_v3_runtime_v2_manager,
        handler._send_visual_json,
    ):
        return True
    if dispatch_p10_spine42_v3_v2_post(
        parts, handler, spine42_v3_v2_manager,
        handler._send_visual_json,
    ):
        return True
    if policy_mutation.dispatch_motion_policy_mutation_post(
        parts, handler, store, handler._send_visual_json,
    ):
        return True
    if dispatch_p10_motion_instance_v3_v2_post(
        parts, handler, motion_instance_v3_v2_manager,
        handler._send_visual_json,
    ):
        return True
    if dispatch_p10_safety_analysis_v2_post(
        parts, handler, safety_analysis_v2_manager,
        handler._send_visual_json,
    ):
        return True
    if dispatch_p10_dynamic_seam_v2_post(
        parts, handler, dynamic_seam_v2_manager,
        handler._send_visual_json,
    ):
        return True
    if dispatch_p10_runtime_capture_post(
        parts, handler, capture_manager, handler._send_visual_json,
    ):
        return True
    if dispatch_motion_policy_preflight_post(
        parts, handler, handler._send_visual_json,
    ):
        return True
    return dispatch_seam_anchor_review_post(
        parts, store, handler, handler._send_visual_json, replay_cache,
    )


__all__ = ["dispatch_workbench_api_post", "dispatch_workbench_api_put"]
