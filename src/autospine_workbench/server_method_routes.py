"""Central method-not-allowed routing for versioned workbench families."""

from __future__ import annotations

from .body_sway_visual_review_routes import is_body_sway_visual_review_path
from . import motion_policy_mutation_routes as policy_mutation
from .motion_policy_preflight_routes import (
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
from .p10_runtime_capture_routes import (
    is_p10_runtime_capture_path,
    send_p10_runtime_capture_method_not_allowed,
)
from .p10_safety_analysis_v2_routes import (
    is_p10_safety_analysis_v2_path,
    send_p10_safety_analysis_v2_method_not_allowed,
)
from .p10_dynamic_seam_v2_routes import (
    is_p10_dynamic_seam_v2_path,
    send_p10_dynamic_seam_v2_method_not_allowed,
)
from .p10_visual_review_v2_routes import (
    is_p10_visual_review_v2_path,
    send_p10_visual_review_v2_method_not_allowed,
)
from .seam_anchor_review_routes import is_seam_anchor_review_path


def send_workbench_route_method_not_allowed(parts, handler) -> None:
    if policy_mutation.is_motion_policy_mutation_path(parts):
        policy_mutation.send_motion_policy_mutation_method_not_allowed(
            parts, handler,
        )
    elif is_motion_policy_preflight_path(parts):
        send_motion_policy_preflight_method_not_allowed(handler)
    elif is_motion_policy_review_package_path(parts):
        send_motion_policy_review_package_method_not_allowed(handler)
    elif is_motion_policy_review_draft_get_path(parts):
        send_motion_policy_review_draft_method_not_allowed(handler)
    elif is_p10_dynamic_seam_v2_path(parts):
        send_p10_dynamic_seam_v2_method_not_allowed(parts, handler)
    elif is_p10_safety_analysis_v2_path(parts):
        send_p10_safety_analysis_v2_method_not_allowed(parts, handler)
    elif is_p10_visual_review_v2_path(parts):
        send_p10_visual_review_v2_method_not_allowed(parts, handler)
    elif is_p10_runtime_capture_path(parts):
        send_p10_runtime_capture_method_not_allowed(parts, handler)
    elif is_body_sway_visual_review_path(parts):
        handler._send_visual_method_not_allowed(parts)
    elif is_seam_anchor_review_path(parts):
        handler._send_seam_anchor_review_method_not_allowed(parts)
    else:
        handler._send_method_not_allowed(
            read_only=handler._mesh_bundle_path(parts),
        )


__all__ = ["send_workbench_route_method_not_allowed"]
