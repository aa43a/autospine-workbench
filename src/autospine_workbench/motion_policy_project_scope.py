"""Strict optional project scope for expensive motion-policy inventories."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

from .project_store import ProjectStore


_PROJECT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class MotionPolicyProjectScopeError(ValueError):
    """Raised when an inventory query contains a non-canonical scope."""


def resolve_motion_policy_project_scope(
    store: ProjectStore, request_target: str | None,
) -> tuple[tuple[str, ...], frozenset[str] | None]:
    """Return projects to hash and an optional exact inventory filter."""

    discovered = store.discover_project_ids()
    if request_target is None:
        return discovered, None
    try:
        query = parse_qs(
            urlsplit(request_target).query,
            keep_blank_values=True,
            strict_parsing=True,
        )
    except ValueError as exc:
        raise MotionPolicyProjectScopeError(
            "Motion-policy project scope is invalid"
        ) from exc
    if not query:
        return discovered, None
    if set(query) != {"project_id"} or len(query["project_id"]) != 1:
        raise MotionPolicyProjectScopeError(
            "Motion-policy project scope is invalid"
        )
    project_id = query["project_id"][0]
    if not _PROJECT_ID.fullmatch(project_id):
        raise MotionPolicyProjectScopeError(
            "Motion-policy project scope is invalid"
        )
    scope = frozenset({project_id})
    selected = (project_id,) if project_id in discovered else ()
    return selected, scope


__all__ = [
    "MotionPolicyProjectScopeError",
    "resolve_motion_policy_project_scope",
]
