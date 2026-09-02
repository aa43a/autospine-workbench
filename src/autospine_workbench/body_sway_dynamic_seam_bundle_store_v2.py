"""Atomic publication for immutable P10.5d v2 evidence bundles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .body_sway_dynamic_seam_bundle_contract_v2 import (
    BodySwayDynamicSeamBundleContractV2Error,
    build_body_sway_dynamic_seam_bundle_contract_v2,
)
from .body_sway_dynamic_seam_bundle_fs_v2 import (
    BodySwayDynamicSeamBundleFSV2Error,
    body_sway_dynamic_seam_bundle_fs_v2,
)
from .immutable_bundle_fs import ImmutableBundleFSError


class BodySwayDynamicSeamBundleStoreV2Error(RuntimeError):
    """Raised when a P10.5d v2 bundle cannot publish exactly once."""


@dataclass(frozen=True, slots=True)
class PublishedBodySwayDynamicSeamBundleV2:
    path: Path
    project_id: str
    clip_id: str
    source_set_sha256: str
    source_document_sha256: str
    probe_sha256: str
    bundle_sha256: str
    reused: bool


class BodySwayDynamicSeamBundleStoreV2:
    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)

    def publish(self, source, probe) -> PublishedBodySwayDynamicSeamBundleV2:
        """Validate before mutation, atomically publish, then exact-read back."""

        try:
            contract = build_body_sway_dynamic_seam_bundle_contract_v2(
                source, probe,
            )
            filesystem = body_sway_dynamic_seam_bundle_fs_v2(
                self.state_root, contract.project_id,
            )
            published = filesystem.publish(
                contract.probe_sha256,
                contract.bundle_sha256,
                contract.document_bytes,
            )
            from .body_sway_dynamic_seam_bundle_reader_v2 import (
                BodySwayDynamicSeamBundleReaderV2,
            )
            verified = BodySwayDynamicSeamBundleReaderV2(
                self.state_root
            ).load(
                contract.project_id,
                contract.probe_sha256,
                contract.bundle_sha256,
            )
            if verified.document_bytes != contract.document_bytes \
                    or verified.source_set_sha256 \
                        != contract.source_set_sha256:
                raise BodySwayDynamicSeamBundleStoreV2Error(
                    "Published dynamic seam v2 bytes differ on readback"
                )
            return PublishedBodySwayDynamicSeamBundleV2(
                published.path, contract.project_id, contract.clip_id,
                contract.source_set_sha256,
                contract.source_document_sha256,
                contract.probe_sha256, contract.bundle_sha256,
                published.reused,
            )
        except BodySwayDynamicSeamBundleStoreV2Error:
            raise
        except (
            BodySwayDynamicSeamBundleContractV2Error,
            BodySwayDynamicSeamBundleFSV2Error,
            ImmutableBundleFSError,
            OSError, RuntimeError, TypeError, ValueError,
        ) as exc:
            raise BodySwayDynamicSeamBundleStoreV2Error(
                "Dynamic seam v2 bundle publication failed"
            ) from exc


__all__ = [
    "BodySwayDynamicSeamBundleStoreV2",
    "BodySwayDynamicSeamBundleStoreV2Error",
    "PublishedBodySwayDynamicSeamBundleV2",
]
