"""Aggregate package-bound motion-policy mutation routes for the server."""

from __future__ import annotations

from typing import Any

from . import capture_framing_routes as capture_framing
from . import motion_policy_adoption_routes as adoption
from . import seam_review_publication_routes as seam_publication
from . import idle_behavior_review_routes as idle_review
from . import region_rebind_adoption_routes as region_rebind
from . import motion_policy_review_draft_routes as draft_policy


def is_motion_policy_mutation_path(parts: list[str]) -> bool:
    return capture_framing.is_capture_framing_mutation_path(parts) \
        or idle_review.is_idle_behavior_review_mutation_path(parts) \
        or draft_policy.is_p9_draft_policy_adoption_path(parts) \
        or adoption.is_motion_policy_adoption_path(parts) \
        or seam_publication.is_seam_review_publication_path(parts) \
        or region_rebind.is_region_rebind_adoption_path(parts)


def motion_policy_mutation_allow_methods(parts: list[str]) -> str:
    if capture_framing.is_capture_framing_mutation_path(parts):
        return capture_framing.ALLOW_METHODS
    if idle_review.is_idle_behavior_review_mutation_path(parts):
        return idle_review.ALLOW_METHODS
    if draft_policy.is_p9_draft_policy_adoption_path(parts):
        return draft_policy.WRITE_METHODS
    if adoption.is_motion_policy_adoption_path(parts):
        return adoption.ALLOW_METHODS
    if seam_publication.is_seam_review_publication_path(parts):
        return seam_publication.ALLOW_METHODS
    if region_rebind.is_region_rebind_adoption_path(parts):
        return region_rebind.ALLOW_METHODS
    return "POST, OPTIONS"


def dispatch_motion_policy_mutation_post(parts, handler, store, send_json):
    return capture_framing.dispatch_capture_framing_post(
        parts, handler, store, send_json,
    ) or idle_review.dispatch_idle_behavior_review_post(
        parts, handler, store, send_json,
    ) or draft_policy.dispatch_p9_draft_policy_adoption_post(
        parts, handler, store, send_json,
    ) or adoption.dispatch_motion_policy_adoption_post(
        parts, handler, store, send_json,
    ) or seam_publication.dispatch_seam_review_publication_post(
        parts, handler, store, send_json,
    ) or region_rebind.dispatch_region_rebind_adoption_post(
        parts, handler, store, send_json,
    )


def send_motion_policy_mutation_method_not_allowed(
    parts: list[str], handler: Any,
) -> None:
    if capture_framing.is_capture_framing_mutation_path(parts):
        capture_framing.send_capture_framing_method_not_allowed(handler)
    elif idle_review.is_idle_behavior_review_mutation_path(parts):
        idle_review.send_idle_behavior_review_method_not_allowed(handler)
    elif draft_policy.is_p9_draft_policy_adoption_path(parts):
        draft_policy.send_motion_policy_review_draft_method_not_allowed(
            handler, write=True,
        )
    elif adoption.is_motion_policy_adoption_path(parts):
        adoption.send_motion_policy_adoption_method_not_allowed(handler)
    elif seam_publication.is_seam_review_publication_path(parts):
        seam_publication.send_seam_review_publication_method_not_allowed(handler)
    else:
        region_rebind.send_region_rebind_adoption_method_not_allowed(handler)
