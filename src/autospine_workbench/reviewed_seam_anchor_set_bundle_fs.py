"""Configured exact-address filesystem for reviewed seam-anchor sets."""

from __future__ import annotations

from pathlib import Path

from .immutable_bundle_fs import ImmutableThreeFileBundleFS
from .manifest_artifacts import LayerManifestError, require_safe_token
from .reviewed_seam_anchor_set_bundle_contract import (
    BUNDLE_ADDRESS_DOMAIN,
    DOCUMENT_LIMITS,
    DOCUMENT_NAMES,
    MAX_TOTAL_BYTES,
)


NAMESPACE = "reviewed-seam-anchor-sets"


class ReviewedSeamAnchorSetBundleFSError(ValueError):
    """Raised when a project-scoped bundle filesystem is ambiguous."""


def reviewed_seam_anchor_set_bundle_fs(
    state_root: Path, project_id: str,
) -> ImmutableThreeFileBundleFS:
    """Return ``builds/project/namespace/set-SHA/bundle-SHA`` storage."""

    try:
        project = require_safe_token(
            project_id, "Reviewed seam-anchor bundle project id"
        )
        return ImmutableThreeFileBundleFS(
            Path(state_root) / "builds" / project,
            namespace=NAMESPACE,
            domain=BUNDLE_ADDRESS_DOMAIN,
            ordered_names=DOCUMENT_NAMES,
            max_file_bytes=max(DOCUMENT_LIMITS),
            max_total_bytes=MAX_TOTAL_BYTES,
        )
    except (LayerManifestError, OSError, TypeError, ValueError) as exc:
        raise ReviewedSeamAnchorSetBundleFSError(
            "Reviewed seam-anchor bundle filesystem address is invalid"
        ) from exc
