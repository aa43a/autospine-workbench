"""Exact P3/P5/P9 replay and P10.0 compilation for idle review."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
import json
from pathlib import Path
from threading import RLock
from typing import Any

from .idle_behavior_candidates import (
    IdleBehaviorCandidates,
    compile_idle_behavior_candidates,
)
from .idle_behavior_review_address import IdleBehaviorReviewAddress
from .idle_behavior_review_replay_cache import (
    load_cached_reviewed_motion_chain,
)
from .manifest_artifacts import LayerManifestError
from .manifest_bundle import LayerManifestBundleReader
from .mesh_bundle_integrity import VerifiedMeshBundle
from .motion_retarget_bundle_integrity import VerifiedMotionRetargetBundle
from .reviewed_motion_bundle_integrity import (
    VerifiedReviewedMotionBundle,
    replay_verified_reviewed_motion_bundle,
)
from .reviewed_motion_bundle_reader import VerifiedReviewedMotionBundleReader
from .reviewed_motion_bundle_run import require_reviewed_motion_bundle_run


class IdleBehaviorReviewReplayError(RuntimeError):
    """Raised when one adopted exact chain cannot be reproduced."""


@dataclass(frozen=True, slots=True)
class IdleBehaviorReviewEvidence:
    """Replayed values needed for the review entry and schematic preview."""

    address: IdleBehaviorReviewAddress
    _manifest_json: str = field(repr=False)
    mesh_bundle: VerifiedMeshBundle
    retarget_bundle: VerifiedMotionRetargetBundle
    reviewed_bundle: VerifiedReviewedMotionBundle
    candidates: IdleBehaviorCandidates

    @property
    def manifest(self) -> dict[str, Any]:
        """Return an isolated manifest copy so cached evidence stays immutable."""

        return json.loads(self._manifest_json)


_MAX_EVIDENCE_ENTRIES = 64
_EVIDENCE_LOCK = RLock()
_EVIDENCE_CACHE: OrderedDict[
    tuple[int, str],
    tuple[object, IdleBehaviorReviewEvidence],
] = OrderedDict()


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
        reader = VerifiedReviewedMotionBundleReader(state)
        chain = load_cached_reviewed_motion_chain(
            state,
            address.project_id,
            address.motion_instance_v2_sha256,
            address.reviewed_motion_bundle_sha256,
            lambda: reader.load_chain(
                address.project_id,
                address.motion_instance_v2_sha256,
                address.reviewed_motion_bundle_sha256,
            ),
        )
        reviewed = chain.reviewed_bundle
        run = reviewed.document("run-manifest.json")
        require_reviewed_motion_bundle_run(run)
        _require_address_binding(address, run)
        return _cached_evidence(state, address, chain)
    except IdleBehaviorReviewReplayError:
        raise
    except _FAILURES as exc:
        raise IdleBehaviorReviewReplayError(
            "The exact idle behavior review chain could not be replayed"
        ) from exc


def clear_idle_behavior_review_evidence_cache() -> None:
    """Clear authority-free derived evidence; used by deterministic tests."""

    with _EVIDENCE_LOCK:
        _EVIDENCE_CACHE.clear()


def _cached_evidence(state, address, chain) -> IdleBehaviorReviewEvidence:
    key = (id(chain), address.package_id)
    with _EVIDENCE_LOCK:
        cached = _EVIDENCE_CACHE.get(key)
        if cached is not None and cached[0] is chain \
                and cached[1].address == address:
            _EVIDENCE_CACHE.move_to_end(key)
            return cached[1]
        evidence = _build_evidence(state, address, chain)
        _EVIDENCE_CACHE[key] = (chain, evidence)
        _EVIDENCE_CACHE.move_to_end(key)
        while len(_EVIDENCE_CACHE) > _MAX_EVIDENCE_ENTRIES:
            _EVIDENCE_CACHE.popitem(last=False)
        return evidence


def _build_evidence(state, address, chain) -> IdleBehaviorReviewEvidence:
    mesh, retarget, reviewed = (
        chain.mesh_bundle, chain.retarget_bundle, chain.reviewed_bundle,
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
    manifest_json = json.dumps(
        manifest, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
    return IdleBehaviorReviewEvidence(
        address, manifest_json, mesh, retarget, reviewed, candidates,
    )


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
