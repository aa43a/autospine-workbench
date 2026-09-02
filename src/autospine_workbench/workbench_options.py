"""Central OPTIONS policy for the loopback workbench API."""

from __future__ import annotations

from http import HTTPStatus

from .body_sway_visual_review_routes import (
    is_body_sway_visual_review_path,
    visual_review_allow_methods,
)
from .motion_policy_preflight_routes import (
    ALLOW_METHODS as MOTION_POLICY_PREFLIGHT_ALLOW_METHODS,
    is_motion_policy_preflight_path,
)
from .motion_policy_review_draft_routes import (
    READ_METHODS as MOTION_POLICY_DRAFT_READ_METHODS,
    is_motion_policy_review_draft_get_path,
)
from .motion_policy_review_package_routes import (
    ALLOW_METHODS as MOTION_POLICY_PACKAGE_ALLOW_METHODS,
    is_motion_policy_review_package_path,
)
from . import motion_policy_mutation_routes as policy_mutation
from .p10_runtime_capture_routes import (
    is_p10_runtime_capture_path,
    p10_runtime_capture_allow_methods,
)
from .p10_safety_analysis_v2_routes import (
    is_p10_safety_analysis_v2_path,
    p10_safety_analysis_v2_allow_methods,
)
from .p10_dynamic_seam_v2_routes import (
    is_p10_dynamic_seam_v2_path, p10_dynamic_seam_v2_allow_methods,
)
from .p10_motion_instance_v3_v2_routes import (
    is_p10_motion_instance_v3_v2_path,
    p10_motion_instance_v3_v2_allow_methods,
)
from .p10_visual_review_v2_routes import (
    is_p10_visual_review_v2_path,
    p10_visual_review_v2_allow_methods,
)
from .seam_anchor_review_routes import (
    is_seam_anchor_review_path,
    seam_anchor_review_resource_methods,
)


def send_workbench_options(parts: list[str], handler) -> None:
    """Send the exact method policy for one already validated local path."""

    body_review = is_body_sway_visual_review_path(parts)
    seam_review = is_seam_anchor_review_path(parts)
    policy_preflight = is_motion_policy_preflight_path(parts)
    adoption = policy_mutation.is_motion_policy_mutation_path(parts)
    policy_package = is_motion_policy_review_package_path(parts)
    policy_draft = is_motion_policy_review_draft_get_path(parts)
    runtime_capture = is_p10_runtime_capture_path(parts)
    safety_analysis_v2 = is_p10_safety_analysis_v2_path(parts)
    dynamic_seam_v2 = is_p10_dynamic_seam_v2_path(parts)
    motion_instance_v3_v2 = is_p10_motion_instance_v3_v2_path(parts)
    visual_review_v2 = is_p10_visual_review_v2_path(parts)
    seam_methods = seam_anchor_review_resource_methods(parts) \
        if seam_review else None
    if seam_review and seam_methods is None:
        handler._send_visual_json(HTTPStatus.NOT_FOUND, {
            "error": "seam_anchor_review_not_found",
            "message": "The exact seam-anchor review resource was not found.",
        })
        return
    local_review = body_review or seam_review or policy_preflight \
        or adoption or policy_package or policy_draft or runtime_capture \
        or safety_analysis_v2 or dynamic_seam_v2 or visual_review_v2 \
        or motion_instance_v3_v2
    methods = _methods(
        parts, handler, body_review=body_review,
        seam_review=seam_review, seam_methods=seam_methods,
        policy_preflight=policy_preflight, adoption=adoption,
        policy_package=policy_package, policy_draft=policy_draft,
        runtime_capture=runtime_capture,
        safety_analysis_v2=safety_analysis_v2,
        dynamic_seam_v2=dynamic_seam_v2,
        motion_instance_v3_v2=motion_instance_v3_v2,
        visual_review_v2=visual_review_v2,
    )
    handler.send_response(HTTPStatus.NO_CONTENT)
    handler._common_headers(visual_review=local_review)
    handler.send_header("Allow", methods)
    handler.send_header("Access-Control-Allow-Methods", methods)
    handler.send_header(
        "Access-Control-Allow-Headers",
        "Content-Type, X-Autospine-Intent" if local_review else "Content-Type",
    )
    handler.send_header("Access-Control-Max-Age", "600")
    handler.send_header("Content-Length", "0")
    handler.end_headers()


def _methods(
    parts, handler, *, body_review, seam_review, seam_methods,
    policy_preflight, adoption, policy_package, policy_draft, runtime_capture,
    safety_analysis_v2, dynamic_seam_v2, motion_instance_v3_v2,
    visual_review_v2,
):
    if motion_instance_v3_v2:
        return p10_motion_instance_v3_v2_allow_methods(parts) or "OPTIONS"
    if dynamic_seam_v2:
        return p10_dynamic_seam_v2_allow_methods(parts) or "OPTIONS"
    if safety_analysis_v2:
        return p10_safety_analysis_v2_allow_methods(parts) or "OPTIONS"
    if visual_review_v2:
        return p10_visual_review_v2_allow_methods(parts) or "OPTIONS"
    if runtime_capture:
        return p10_runtime_capture_allow_methods(parts) or "OPTIONS"
    if adoption:
        return policy_mutation.motion_policy_mutation_allow_methods(parts)
    if policy_preflight:
        return MOTION_POLICY_PREFLIGHT_ALLOW_METHODS
    if policy_package:
        return MOTION_POLICY_PACKAGE_ALLOW_METHODS
    if policy_draft:
        return MOTION_POLICY_DRAFT_READ_METHODS
    if body_review:
        return visual_review_allow_methods(parts)
    if seam_review:
        return seam_methods
    if handler._mesh_bundle_path(parts):
        return "GET, HEAD, OPTIONS"
    return "GET, HEAD, PUT, OPTIONS"


__all__ = ["send_workbench_options"]
