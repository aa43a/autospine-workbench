"""Aggregate package-bound motion-policy mutation routes for the server."""

from __future__ import annotations

from typing import Any

from . import motion_policy_adoption_routes as adoption
from . import seam_review_publication_routes as seam_publication


def is_motion_policy_mutation_path(parts: list[str]) -> bool:
    return adoption.is_motion_policy_adoption_path(parts) \
        or seam_publication.is_seam_review_publication_path(parts)


def motion_policy_mutation_allow_methods(parts: list[str]) -> str:
    if adoption.is_motion_policy_adoption_path(parts):
        return adoption.ALLOW_METHODS
    if seam_publication.is_seam_review_publication_path(parts):
        return seam_publication.ALLOW_METHODS
    return "POST, OPTIONS"


def dispatch_motion_policy_mutation_post(parts, handler, store, send_json):
    return adoption.dispatch_motion_policy_adoption_post(
        parts, handler, store, send_json,
    ) or seam_publication.dispatch_seam_review_publication_post(
        parts, handler, store, send_json,
    )


def send_motion_policy_mutation_method_not_allowed(
    parts: list[str], handler: Any,
) -> None:
    if adoption.is_motion_policy_adoption_path(parts):
        adoption.send_motion_policy_adoption_method_not_allowed(handler)
    else:
        seam_publication.send_seam_review_publication_method_not_allowed(handler)
