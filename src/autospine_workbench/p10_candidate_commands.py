"""Exact-read application service for P10 idle-behavior candidates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .idle_behavior_candidates import (
    IdleBehaviorCandidateError,
    compile_idle_behavior_candidates,
)
from .manifest_bundle import (
    LayerManifestBundleError,
    LayerManifestBundleReader,
)
from .mesh_bundle_reader import (
    VerifiedMeshBundleReader,
    VerifiedMeshBundleReaderError,
)
from .motion_retarget_bundle_reader import (
    VerifiedMotionRetargetBundleReader,
    VerifiedMotionRetargetBundleReaderError,
)
from .reviewed_motion_bundle_contract import ReviewedMotionBundleContractError
from .reviewed_motion_bundle_integrity import (
    ReviewedMotionBundleIntegrityError,
    replay_verified_reviewed_motion_bundle,
)
from .reviewed_motion_bundle_reader import (
    VerifiedReviewedMotionBundleReader,
    VerifiedReviewedMotionBundleReaderError,
)
from .reviewed_motion_bundle_upstream import ReviewedMotionBundleUpstreamError
from .safe_input_files import SafeInputFileError


class P10CandidateCommandError(RuntimeError):
    """Raised when one exact P10 candidate compilation cannot finish."""


@dataclass(frozen=True, slots=True)
class P10CandidateCommandResult:
    """Canonical candidate document plus every exact input path read."""

    input_paths: tuple[Path, ...]
    idle_behavior_candidates_sha256: str
    document: dict[str, Any]


def compile_idle_behavior_candidates_command(
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
) -> P10CandidateCommandResult:
    """Read four exact bundles, replay P9, then invoke the pure compiler."""

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
        compiled = compile_idle_behavior_candidates(
            manifest.manifest, mesh, retarget, contract
        )
        return P10CandidateCommandResult(
            input_paths=(
                manifest.path, mesh.path, retarget.path, reviewed.path,
            ),
            idle_behavior_candidates_sha256=compiled.sha256,
            document=compiled.document,
        )
    except P10CandidateCommandError:
        raise
    except _ERRORS as exc:
        raise P10CandidateCommandError(
            f"Idle behavior candidate command failed: {exc}"
        ) from exc

_ERRORS = (
    AttributeError,
    IdleBehaviorCandidateError,
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
