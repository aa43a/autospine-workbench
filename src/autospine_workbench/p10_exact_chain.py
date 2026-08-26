"""Reusable exact-address state-tree loader for P10 application services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .manifest_bundle import (
    LayerManifestBundleError,
    LayerManifestBundleReader,
)
from .mesh_bundle_integrity import VerifiedMeshBundle
from .mesh_bundle_reader import (
    VerifiedMeshBundleReader,
    VerifiedMeshBundleReaderError,
)
from .motion_retarget_bundle_integrity import VerifiedMotionRetargetBundle
from .motion_retarget_bundle_reader import (
    VerifiedMotionRetargetBundleReader,
    VerifiedMotionRetargetBundleReaderError,
)
from .reviewed_motion_bundle_contract import (
    ReviewedMotionBundleContract,
    ReviewedMotionBundleContractError,
)
from .reviewed_motion_bundle_integrity import (
    ReviewedMotionBundleIntegrityError,
    VerifiedReviewedMotionBundle,
    replay_verified_reviewed_motion_bundle,
)
from .reviewed_motion_bundle_reader import (
    VerifiedReviewedMotionBundleReader,
    VerifiedReviewedMotionBundleReaderError,
)
from .reviewed_motion_bundle_upstream import ReviewedMotionBundleUpstreamError
from .safe_input_files import SafeInputFileError


class P10ExactChainError(RuntimeError):
    """Raised when any explicit P10 address cannot form one exact chain."""


@dataclass(frozen=True, slots=True)
class P10ExactChain:
    """Four exact input paths and their replayed P3/P5/P9 values."""

    input_paths: tuple[Path, ...]
    manifest: dict[str, Any]
    mesh_bundle: VerifiedMeshBundle
    retarget_bundle: VerifiedMotionRetargetBundle
    reviewed_bundle: VerifiedReviewedMotionBundle
    reviewed_contract: ReviewedMotionBundleContract


def load_p10_exact_chain(
    state_root: Path,
    project_id: str,
    *,
    layer_manifest_sha256: str,
    p3_rig_sha256: str,
    p3_bundle_sha256: str,
    motion_instance_sha256: str,
    motion_retarget_bundle_sha256: str,
    motion_instance_v2_sha256: str,
    reviewed_motion_bundle_sha256: str,
) -> P10ExactChain:
    """Load only seven explicit addresses, then replay the exact P9 contract."""

    try:
        state = Path(state_root)
        manifest = LayerManifestBundleReader(state).load(
            project_id, layer_manifest_sha256
        )
        mesh = VerifiedMeshBundleReader(state).load(
            project_id, p3_rig_sha256, p3_bundle_sha256
        )
        retarget = VerifiedMotionRetargetBundleReader(state).load(
            project_id,
            motion_instance_sha256,
            motion_retarget_bundle_sha256,
        )
        reviewed = VerifiedReviewedMotionBundleReader(state).load(
            project_id,
            motion_instance_v2_sha256,
            reviewed_motion_bundle_sha256,
            mesh_bundle=mesh,
            retarget_bundle=retarget,
        )
        contract = replay_verified_reviewed_motion_bundle(
            reviewed, mesh, retarget
        )
        return P10ExactChain(
            input_paths=(
                manifest.path, mesh.path, retarget.path, reviewed.path,
            ),
            manifest=manifest.manifest,
            mesh_bundle=mesh,
            retarget_bundle=retarget,
            reviewed_bundle=reviewed,
            reviewed_contract=contract,
        )
    except P10ExactChainError:
        raise
    except _ERRORS as exc:
        # Preserve the underlying reader/replay text for existing CLI semantics.
        raise P10ExactChainError(str(exc)) from exc


_ERRORS = (
    AttributeError,
    KeyError,
    LayerManifestBundleError,
    OSError,
    OverflowError,
    RecursionError,
    ReviewedMotionBundleContractError,
    ReviewedMotionBundleIntegrityError,
    ReviewedMotionBundleUpstreamError,
    SafeInputFileError,
    TypeError,
    UnicodeError,
    ValueError,
    VerifiedMeshBundleReaderError,
    VerifiedMotionRetargetBundleReaderError,
    VerifiedReviewedMotionBundleReaderError,
)
