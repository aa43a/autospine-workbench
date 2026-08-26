"""Atomic immutable publication for ProjectedMotionIR bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .immutable_bundle_fs import ImmutableBundleFSError
from .projected_motion_bundle_contract import (
    ProjectedMotionBundleContractError,
    build_projected_motion_bundle_contract,
)
from .projected_motion_bundle_fs import projected_motion_bundle_fs


class ProjectedMotionBundleStoreError(RuntimeError):
    """Raised when a projected bundle cannot be published safely."""


@dataclass(frozen=True, slots=True)
class PublishedProjectedMotionBundle:
    path: Path
    clip_id: str
    projected_motion_sha256: str
    camera_sha256: str
    run_sha256: str
    legacy_motion_sha256: str
    bundle_sha256: str
    reused: bool


class ProjectedMotionBundleStore:
    """Publish a fixed three-document inventory under two exact SHAs."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)

    def publish(
        self,
        camera: Mapping[str, Any],
        projected_motion: Mapping[str, Any],
        run_manifest: Mapping[str, Any],
    ) -> PublishedProjectedMotionBundle:
        try:
            contract = build_projected_motion_bundle_contract(
                camera, projected_motion, run_manifest
            )
            published = projected_motion_bundle_fs(self.state_root).publish(
                contract.projected_motion_sha256,
                contract.bundle_sha256,
                contract.document_bytes,
            )
            return PublishedProjectedMotionBundle(
                path=published.path,
                clip_id=contract.clip_id,
                projected_motion_sha256=contract.projected_motion_sha256,
                camera_sha256=contract.camera_sha256,
                run_sha256=contract.run_sha256,
                legacy_motion_sha256=contract.legacy_motion_sha256,
                bundle_sha256=contract.bundle_sha256,
                reused=published.reused,
            )
        except ProjectedMotionBundleStoreError:
            raise
        except (
            ImmutableBundleFSError,
            ProjectedMotionBundleContractError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            raise ProjectedMotionBundleStoreError(
                f"Projected motion bundle publication failed: {exc}"
            ) from exc
