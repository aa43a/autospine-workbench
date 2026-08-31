"""Package-centric exact application service for P10.3 Preview v2."""

from __future__ import annotations

from .p10_preview_v2_result import (
    PUBLIC_FIELDS,
    P10PreviewV2CommandError,
    P10PreviewV2CommandResult,
)
from .p10_preview_v2_service import compile_cached_body_sway_preview_v2
from .project_store import ProjectStore
from .temporary_body_sway_preview_v2 import TemporaryBodySwayPreviewV2


def compile_body_sway_preview_v2_for_package(
    store: ProjectStore, package_id: str,
) -> P10PreviewV2CommandResult:
    """Return an exact result, reusing only revalidated process-local bytes."""

    return compile_cached_body_sway_preview_v2(store, package_id)


def require_exact_preview_v2_for_mount(
    result: P10PreviewV2CommandResult,
) -> TemporaryBodySwayPreviewV2:
    """Revalidate the current package before exposing cached mount bytes."""

    if type(result) is not P10PreviewV2CommandResult:
        raise P10PreviewV2CommandError("Preview v2 command result is invalid")
    store = ProjectStore(result._workspace_root, state_root=result._state_root)
    replay = compile_body_sway_preview_v2_for_package(
        store, result.package_id,
    )
    for field_name in PUBLIC_FIELDS:
        if getattr(result, field_name) != getattr(replay, field_name):
            raise P10PreviewV2CommandError(
                f"Preview v2 {field_name} changed during mount replay"
            )
    if result._preview.canonical_bytes != replay._preview.canonical_bytes \
            or result._preview.artifact_bytes != replay._preview.artifact_bytes:
        raise P10PreviewV2CommandError(
            "Preview v2 bytes changed during mount replay"
        )
    return replay._preview


__all__ = [
    "P10PreviewV2CommandError", "P10PreviewV2CommandResult",
    "compile_body_sway_preview_v2_for_package",
    "require_exact_preview_v2_for_mount",
]
