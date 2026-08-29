"""Exact P3/P5/P9 replay and P10.0 compilation for idle review."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .idle_behavior_candidates import (
    IdleBehaviorCandidates,
    compile_idle_behavior_candidates,
)
from .idle_behavior_review_address import IdleBehaviorReviewAddress
from .manifest_artifacts import LayerManifestError
from .manifest_bundle import LayerManifestBundleReader
from .mesh_bundle_integrity import VerifiedMeshBundle
from .mesh_bundle_reader import VerifiedMeshBundleReader
from .motion_retarget_bundle_integrity import VerifiedMotionRetargetBundle
from .motion_retarget_bundle_reader import VerifiedMotionRetargetBundleReader
from .reviewed_motion_bundle_contract import (
    reviewed_motion_bundle_address_sha256,
)
from .reviewed_motion_bundle_files import (
    existing_bundle_path,
    read_bundle_files,
)
from .reviewed_motion_bundle_integrity import (
    VerifiedReviewedMotionBundle,
    replay_verified_reviewed_motion_bundle,
)
from .reviewed_motion_bundle_reader import VerifiedReviewedMotionBundleReader
from .reviewed_motion_bundle_run import require_reviewed_motion_bundle_run
from .safe_input_files import strict_json_object


class IdleBehaviorReviewReplayError(RuntimeError):
    """Raised when one adopted exact chain cannot be reproduced."""


@dataclass(frozen=True, slots=True)
class IdleBehaviorReviewEvidence:
    """Replayed values needed for the review entry and schematic preview."""

    address: IdleBehaviorReviewAddress
    manifest: dict[str, Any]
    mesh_bundle: VerifiedMeshBundle
    retarget_bundle: VerifiedMotionRetargetBundle
    reviewed_bundle: VerifiedReviewedMotionBundle
    candidates: IdleBehaviorCandidates


def replay_idle_behavior_review_package(
    state_root: Path, address: IdleBehaviorReviewAddress,
) -> IdleBehaviorReviewEvidence:
    """Resolve no aliases: snapshot the P9 run, then replay every exact input."""

    try:
        if type(address) is not IdleBehaviorReviewAddress:
            raise IdleBehaviorReviewReplayError(
                "Idle behavior review requires an exact package address"
            )
        state = Path(state_root)
        directory = existing_bundle_path(
            state, address.project_id,
            address.motion_instance_v2_sha256,
            address.reviewed_motion_bundle_sha256,
        )
        items = read_bundle_files(directory)
        if reviewed_motion_bundle_address_sha256(
            address.project_id, address.motion_instance_v2_sha256, items,
        ) != address.reviewed_motion_bundle_sha256:
            raise IdleBehaviorReviewReplayError(
                "Reviewed-motion snapshot differs from its exact address"
            )
        run = strict_json_object(
            dict(items)["run-manifest.json"], "Reviewed-motion run manifest"
        )
        require_reviewed_motion_bundle_run(run)
        _require_address_binding(address, run)
        inputs = run["inputs"]
        mesh = VerifiedMeshBundleReader(state).load(
            address.project_id,
            inputs["p3"]["rig_sha256"],
            inputs["p3"]["bundle_sha256"],
        )
        retarget = VerifiedMotionRetargetBundleReader(state).load(
            address.project_id,
            inputs["p5"]["instance_sha256"],
            inputs["p5"]["bundle_sha256"],
        )
        reviewed = VerifiedReviewedMotionBundleReader(state).load(
            address.project_id,
            address.motion_instance_v2_sha256,
            address.reviewed_motion_bundle_sha256,
            mesh_bundle=mesh,
            retarget_bundle=retarget,
        )
        contract = replay_verified_reviewed_motion_bundle(
            reviewed, mesh, retarget,
        )
        manifest = LayerManifestBundleReader(state).load(
            address.project_id, mesh.layer_manifest_sha256,
        ).manifest
        candidates = compile_idle_behavior_candidates(
            manifest, mesh, retarget, contract,
        )
        if candidates.document["clip_id"] != address.clip_id:
            raise IdleBehaviorReviewReplayError(
                "Idle behavior candidates differ from the selected clip"
            )
        return IdleBehaviorReviewEvidence(
            address, manifest, mesh, retarget, reviewed, candidates,
        )
    except IdleBehaviorReviewReplayError:
        raise
    except _FAILURES as exc:
        raise IdleBehaviorReviewReplayError(
            "The exact idle behavior review chain could not be replayed"
        ) from exc


def _require_address_binding(address, run) -> None:
    inputs, outputs = run["inputs"], run["outputs"]
    if run["project_id"] != address.project_id \
            or run["clip_id"] != address.clip_id \
            or inputs["motion_policy_decision_sha256"] \
                != address.p9_decision_sha256 \
            or outputs["motion_instance_v2_sha256"] \
                != address.motion_instance_v2_sha256:
        raise IdleBehaviorReviewReplayError(
            "Reviewed-motion run differs from the selected adoption"
        )


_FAILURES = (
    AttributeError, KeyError, LayerManifestError, OSError, OverflowError,
    RuntimeError, TypeError, UnicodeError, ValueError,
)
