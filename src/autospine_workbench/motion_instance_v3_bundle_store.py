"""Atomic immutable publication for MotionInstance v3 bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

from .atomic_staging import create_same_parent_staging
from .body_sway_dynamic_seam_head_checks import (
    require_current_body_sway_dynamic_seam_heads,
)
from .motion_instance_v3_bundle_contract import (
    MotionInstanceV3BundleContract,
    MotionInstanceV3BundleContractError,
    build_motion_instance_v3_bundle_contract,
)
from .motion_instance_v3_bundle_files import (
    MotionInstanceV3BundleFilesError,
    existing_exact_child,
    publication_parent,
    read_bundle_files,
    remove_staging,
    require_real_directory,
    sync_directory,
    write_file,
)
from .motion_instance_v3_bundle_integrity import (
    MotionInstanceV3BundleIntegrityError,
    MotionInstanceV3BundleSnapshot,
    verify_motion_instance_v3_bundle_snapshot,
)
from .reviewed_motion_bundle_integrity import VerifiedReviewedMotionBundle


class MotionInstanceV3BundleStoreError(RuntimeError):
    """Raised when a v3 bundle cannot be published safely."""


@dataclass(frozen=True, slots=True)
class PublishedMotionInstanceV3Bundle:
    path: Path
    project_id: str
    clip_id: str
    motion_instance_v3_sha256: str
    bundle_sha256: str
    run_sha256: str
    reused: bool


class MotionInstanceV3BundleStore:
    """Publish three exact documents under project/v3/bundle addresses."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)

    def publish(
        self,
        project_id: str,
        admission: Mapping[str, Any],
        motion_instance_v3: Mapping[str, Any],
        reviewed_bundle: VerifiedReviewedMotionBundle,
    ) -> PublishedMotionInstanceV3Bundle:
        """Seal current review heads around validation before any filesystem write."""

        try:
            dynamic_source = admission["source"][
                "body_sway_dynamic_seam_probe"
            ]["source"]
            before = require_current_body_sway_dynamic_seam_heads(
                self.state_root, dynamic_source
            )
            contract = build_motion_instance_v3_bundle_contract(
                project_id, admission, motion_instance_v3, reviewed_bundle
            )
            after = require_current_body_sway_dynamic_seam_heads(
                self.state_root, dynamic_source
            )
            if before.identity != after.identity \
                    or before.canonical_bytes != after.canonical_bytes:
                raise MotionInstanceV3BundleStoreError(
                    "MotionInstance v3 review heads drifted before publication"
                )
        except MotionInstanceV3BundleStoreError:
            raise
        except (
            AttributeError, KeyError, MotionInstanceV3BundleContractError,
            OSError, OverflowError, RuntimeError, TypeError, ValueError,
        ) as exc:
            raise MotionInstanceV3BundleStoreError(
                "MotionInstance v3 publication input or head authority is invalid"
            ) from exc
        parent: Path | None = None
        staging: Path | None = None
        try:
            parent = publication_parent(
                self.state_root, contract.project_id,
                contract.motion_instance_v3_sha256,
            )
            existing = existing_exact_child(parent, contract.bundle_sha256)
            if existing is not None:
                _verify(existing, contract, reviewed_bundle)
                return _published(existing, contract, reused=True)
            staging = create_same_parent_staging(
                parent, prefix=f".{contract.bundle_sha256[:12]}.",
            )
            require_real_directory(
                staging, "MotionInstance v3 staging directory"
            )
            for name, data in contract.document_bytes.items():
                write_file(staging / name, data)
            _verify(staging, contract, reviewed_bundle, staging=True)
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
                _verify(destination, contract, reviewed_bundle)
                reused = True
            _verify(destination, contract, reviewed_bundle)
            return _published(destination, contract, reused=reused)
        except MotionInstanceV3BundleStoreError:
            raise
        except (
            MotionInstanceV3BundleFilesError,
            MotionInstanceV3BundleIntegrityError, OSError, RuntimeError,
            TypeError, ValueError,
        ) as exc:
            raise MotionInstanceV3BundleStoreError(
                "Could not atomically publish MotionInstance v3 bundle"
            ) from exc
        finally:
            if staging is not None:
                remove_staging(staging, parent)


def _verify(
    directory: Path,
    contract: MotionInstanceV3BundleContract,
    reviewed_bundle: VerifiedReviewedMotionBundle,
    *,
    staging: bool = False,
) -> None:
    items = read_bundle_files(directory)
    verified = verify_motion_instance_v3_bundle_snapshot(
        MotionInstanceV3BundleSnapshot(directory, items),
        expected_project_id=contract.project_id,
        expected_motion_instance_v3_sha256=
            contract.motion_instance_v3_sha256,
        expected_bundle_sha256=contract.bundle_sha256,
        reviewed_bundle=reviewed_bundle,
        require_address_path=not staging,
    )
    if verified.document_bytes != contract.document_bytes \
            or verified.identities != contract.identities:
        raise MotionInstanceV3BundleStoreError(
            "MotionInstance v3 directory differs from its exact contract"
        )


def _published(path, contract, *, reused) -> PublishedMotionInstanceV3Bundle:
    return PublishedMotionInstanceV3Bundle(
        path, contract.project_id, contract.clip_id,
        contract.motion_instance_v3_sha256, contract.bundle_sha256,
        contract.run_sha256, reused,
    )


__all__ = [
    "MotionInstanceV3BundleStore", "MotionInstanceV3BundleStoreError",
    "PublishedMotionInstanceV3Bundle",
]
