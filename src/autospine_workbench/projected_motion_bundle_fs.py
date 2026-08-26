"""Configured filesystem boundary for exact ProjectedMotionIR bundles."""

from __future__ import annotations

from pathlib import Path

from .immutable_bundle_fs import ImmutableThreeFileBundleFS
from .projected_motion_bundle_contract import (
    BUNDLE_ADDRESS_DOMAIN,
    DOCUMENT_LIMITS,
    DOCUMENT_NAMES,
    MAX_TOTAL_BYTES,
)


NAMESPACE = "projected-motions"


def projected_motion_bundle_fs(state_root: Path) -> ImmutableThreeFileBundleFS:
    """Return a fresh exact-address filesystem configured for P8."""

    return ImmutableThreeFileBundleFS(
        state_root,
        namespace=NAMESPACE,
        domain=BUNDLE_ADDRESS_DOMAIN,
        ordered_names=DOCUMENT_NAMES,
        max_file_bytes=max(DOCUMENT_LIMITS),
        max_total_bytes=MAX_TOTAL_BYTES,
    )
