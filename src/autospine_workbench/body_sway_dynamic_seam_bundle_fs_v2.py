"""Project-scoped immutable filesystem for P10.5d v2 bundles."""

from __future__ import annotations

from pathlib import Path

from .body_sway_dynamic_seam_bundle_contract_v2 import (
    BUNDLE_ADDRESS_DOMAIN,
    DOCUMENT_NAMES,
    MAX_FILE_BYTES,
    MAX_TOTAL_BYTES,
)
from .immutable_bundle_fs import ImmutableThreeFileBundleFS
from .manifest_artifacts import LayerManifestError, require_safe_token


NAMESPACE = "body-sway-dynamic-seam-v2"


class BodySwayDynamicSeamBundleFSV2Error(ValueError):
    """Raised when a P10.5d v2 bundle address is ambiguous."""


def body_sway_dynamic_seam_bundle_fs_v2(
    state_root: Path, project_id: str,
) -> ImmutableThreeFileBundleFS:
    try:
        project = require_safe_token(project_id, "Dynamic seam v2 project")
        return ImmutableThreeFileBundleFS(
            Path(state_root) / "builds" / project,
            namespace=NAMESPACE,
            domain=BUNDLE_ADDRESS_DOMAIN,
            ordered_names=DOCUMENT_NAMES,
            max_file_bytes=MAX_FILE_BYTES,
            max_total_bytes=MAX_TOTAL_BYTES,
        )
    except (LayerManifestError, OSError, TypeError, ValueError) as exc:
        raise BodySwayDynamicSeamBundleFSV2Error(
            "Dynamic seam v2 bundle filesystem address is invalid"
        ) from exc


__all__ = [
    "BodySwayDynamicSeamBundleFSV2Error",
    "NAMESPACE",
    "body_sway_dynamic_seam_bundle_fs_v2",
]
