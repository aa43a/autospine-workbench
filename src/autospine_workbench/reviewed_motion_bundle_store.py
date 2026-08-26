"""Atomic immutable publication for reviewed-motion bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
from typing import Any

from .mesh_bundle_integrity import VerifiedMeshBundle
from .motion_retarget_bundle_integrity import VerifiedMotionRetargetBundle
from .reviewed_motion_bundle_contract import (
    ReviewedMotionBundleContract,
    ReviewedMotionBundleContractError,
    build_reviewed_motion_bundle_contract,
)
from .reviewed_motion_bundle_files import (
    ReviewedMotionBundleFilesError,
    existing_exact_child,
    publication_parent,
    read_bundle_files,
    remove_staging,
    require_real_directory,
    sync_directory,
    write_file,
)
from .reviewed_motion_bundle_integrity import (
    ReviewedMotionBundleIntegrityError,
    ReviewedMotionBundleSnapshot,
    verify_reviewed_motion_bundle_snapshot,
)
from .reviewed_motion_bundle_upstream import (
    ReviewedMotionBundleUpstreamError,
    require_reviewed_motion_upstreams,
)


class ReviewedMotionBundleStoreError(RuntimeError):
    """Raised when a reviewed-motion bundle cannot be published safely."""


@dataclass(frozen=True, slots=True)
class PublishedReviewedMotionBundle:
    path: Path
    project_id: str
    clip_id: str
    motion_instance_v2_sha256: str
    bundle_sha256: str
    run_sha256: str
    reused: bool


class ReviewedMotionBundleStore:
    """Publish six exact documents under project/v2/bundle address levels."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)

    def publish(
        self,
        project_id: str,
        foot_candidates: Mapping[str, Any],
        depth_candidates: Mapping[str, Any],
        decision: Mapping[str, Any],
        reviewed_policy: Mapping[str, Any],
        motion_instance_v2: Mapping[str, Any],
        mesh_bundle: VerifiedMeshBundle,
        retarget_bundle: VerifiedMotionRetargetBundle,
    ) -> PublishedReviewedMotionBundle:
        """Validate fully before creating any state directory or staging file."""

        try:
            base, target = require_reviewed_motion_upstreams(
                mesh_bundle, retarget_bundle
            )
            contract = build_reviewed_motion_bundle_contract(
                project_id, foot_candidates, depth_candidates, decision,
                reviewed_policy, motion_instance_v2, mesh_bundle, base, target,
            )
        except (
            ReviewedMotionBundleContractError,
            ReviewedMotionBundleUpstreamError,
        ) as exc:
            raise ReviewedMotionBundleStoreError(
                "Reviewed-motion publication input is invalid"
            ) from exc
        parent: Path | None = None
        staging: Path | None = None
        try:
            parent = publication_parent(
                self.state_root, contract.project_id,
                contract.motion_instance_v2_sha256,
            )
            existing = existing_exact_child(parent, contract.bundle_sha256)
            if existing is not None:
                _verify(existing, contract, mesh_bundle, retarget_bundle)
                return _published(existing, contract, reused=True)
            staging = Path(tempfile.mkdtemp(
                prefix=f".{contract.bundle_sha256[:12]}.", dir=parent,
            ))
            require_real_directory(staging, "Reviewed-motion staging directory")
            for name, data in contract.document_bytes.items():
                write_file(staging / name, data)
            _verify(
                staging, contract, mesh_bundle, retarget_bundle,
                staging=True,
            )
            sync_directory(staging)
            try:
                destination = parent / contract.bundle_sha256
                os.rename(staging, destination)
                staging = None
                sync_directory(parent)
                reused = False
            except OSError:
                destination = existing_exact_child(
                    parent, contract.bundle_sha256
                )
                if destination is None:
                    raise
                _verify(destination, contract, mesh_bundle, retarget_bundle)
                reused = True
            _verify(destination, contract, mesh_bundle, retarget_bundle)
            return _published(destination, contract, reused=reused)
        except ReviewedMotionBundleStoreError:
            raise
        except (
            OSError, ReviewedMotionBundleFilesError,
            ReviewedMotionBundleIntegrityError, RuntimeError,
            TypeError, ValueError,
        ) as exc:
            raise ReviewedMotionBundleStoreError(
                "Could not atomically publish reviewed-motion bundle"
            ) from exc
        finally:
            if staging is not None:
                remove_staging(staging, parent)


def _verify(
    directory: Path,
    contract: ReviewedMotionBundleContract,
    mesh_bundle: VerifiedMeshBundle,
    retarget_bundle: VerifiedMotionRetargetBundle,
    *,
    staging: bool = False,
) -> None:
    items = read_bundle_files(directory)
    verified = verify_reviewed_motion_bundle_snapshot(
        ReviewedMotionBundleSnapshot(directory, items),
        expected_project_id=contract.project_id,
        expected_motion_instance_v2_sha256=contract.motion_instance_v2_sha256,
        expected_bundle_sha256=contract.bundle_sha256,
        mesh_bundle=mesh_bundle,
        retarget_bundle=retarget_bundle,
        require_address_path=not staging,
    )
    if verified.document_bytes != contract.document_bytes \
            or verified.identities != contract.identities:
        raise ReviewedMotionBundleStoreError(
            "Reviewed-motion directory differs from its exact contract"
        )


def _published(path, contract, *, reused) -> PublishedReviewedMotionBundle:
    return PublishedReviewedMotionBundle(
        path, contract.project_id, contract.clip_id,
        contract.motion_instance_v2_sha256, contract.bundle_sha256,
        contract.run_sha256, reused,
    )
