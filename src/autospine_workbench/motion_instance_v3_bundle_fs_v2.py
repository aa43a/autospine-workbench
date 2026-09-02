"""Project-scoped immutable filesystem for P10.6b v2 bundles."""

from __future__ import annotations

from pathlib import Path

from .immutable_bundle_fs import ImmutableThreeFileBundleFS
from .manifest_artifacts import LayerManifestError, require_safe_token


NAMESPACE = "body-sway-motion-instance-v3-v2"


class MotionInstanceV3BundleFSV2Error(ValueError):
    """Raised when a P10.6b v2 filesystem address is ambiguous."""


def motion_instance_v3_bundle_fs_v2(
    state_root: Path,
    project_id: str,
) -> ImmutableThreeFileBundleFS:
    """Return the isolated v2 filesystem without touching frozen v1."""

    from .motion_instance_v3_bundle_contract_v2 import (
        BUNDLE_ADDRESS_DOMAIN,
        DOCUMENT_NAMES,
        MAX_FILE_BYTES,
        MAX_TOTAL_BYTES,
    )

    try:
        project = require_safe_token(project_id, "MotionInstance v3 v2 project")
        return ImmutableThreeFileBundleFS(
            Path(state_root) / "builds" / project,
            namespace=NAMESPACE,
            domain=BUNDLE_ADDRESS_DOMAIN,
            ordered_names=DOCUMENT_NAMES,
            max_file_bytes=MAX_FILE_BYTES,
            max_total_bytes=MAX_TOTAL_BYTES,
        )
    except (LayerManifestError, OSError, TypeError, ValueError) as exc:
        raise MotionInstanceV3BundleFSV2Error(
            "MotionInstance v3 v2 bundle filesystem address is invalid"
        ) from exc


__all__ = [
    "MotionInstanceV3BundleFSV2Error",
    "NAMESPACE",
    "motion_instance_v3_bundle_fs_v2",
]
