"""Exact semantic replay for immutable reviewed-motion snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .mesh_bundle_integrity import VerifiedMeshBundle
from .motion_retarget_bundle_integrity import VerifiedMotionRetargetBundle
from .reviewed_motion_bundle_contract import (
    DOCUMENT_LIMITS,
    DOCUMENT_NAMES,
    MAX_TOTAL_DOCUMENT_BYTES,
    ReviewedMotionBundleContractError,
    build_reviewed_motion_bundle_contract,
)
from .reviewed_motion_bundle_files import NAMESPACE
from .reviewed_motion_bundle_upstream import (
    ReviewedMotionBundleUpstreamError,
    require_reviewed_motion_upstreams,
)
from .safe_input_files import SafeInputFileError, strict_json_object


class ReviewedMotionBundleIntegrityError(ValueError):
    """Raised when stored bytes cannot be replayed from exact P3/P5 inputs."""


@dataclass(frozen=True, slots=True)
class ReviewedMotionBundleSnapshot:
    """One read of each fixed-inventory file in a secured directory."""

    path: Path
    document_items: tuple[tuple[str, bytes], ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class VerifiedReviewedMotionBundle:
    """Frozen verified identities with isolated JSON document access."""

    path: Path
    project_id: str
    clip_id: str
    foot_lock_candidates_sha256: str
    depth_order_candidates_sha256: str
    motion_policy_decision_sha256: str
    reviewed_motion_policy_sha256: str
    motion_instance_v2_sha256: str
    run_sha256: str
    bundle_sha256: str
    _document_items: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def inventory(self) -> tuple[str, ...]:
        return tuple(name for name, _data in self._document_items)

    @property
    def document_bytes(self) -> dict[str, bytes]:
        return dict(self._document_items)

    @property
    def identities(self) -> dict[str, str]:
        return {
            "foot_lock_candidates_sha256": self.foot_lock_candidates_sha256,
            "depth_order_candidates_sha256": self.depth_order_candidates_sha256,
            "motion_policy_decision_sha256": self.motion_policy_decision_sha256,
            "reviewed_motion_policy_sha256": self.reviewed_motion_policy_sha256,
            "motion_instance_v2_sha256": self.motion_instance_v2_sha256,
            "run_sha256": self.run_sha256,
            "bundle_sha256": self.bundle_sha256,
        }

    def document(self, name: str) -> dict[str, Any]:
        try:
            return json.loads(dict(self._document_items)[name])
        except KeyError as exc:
            raise KeyError(name) from exc


def verify_reviewed_motion_bundle_snapshot(
    snapshot: ReviewedMotionBundleSnapshot,
    *,
    expected_project_id: str,
    expected_motion_instance_v2_sha256: str,
    expected_bundle_sha256: str,
    mesh_bundle: VerifiedMeshBundle,
    retarget_bundle: VerifiedMotionRetargetBundle,
    require_address_path: bool = True,
) -> VerifiedReviewedMotionBundle:
    """Rebuild policy and v2 outputs, then compare every exact stored byte."""

    try:
        if type(snapshot) is not ReviewedMotionBundleSnapshot:
            raise ReviewedMotionBundleIntegrityError(
                "Reviewed-motion snapshot type is invalid"
            )
        raw = _exact_items(snapshot.document_items)
        documents = {
            name: strict_json_object(raw[name], name) for name in DOCUMENT_NAMES
        }
        base_instance, target_profile = require_reviewed_motion_upstreams(
            mesh_bundle, retarget_bundle
        )
        contract = build_reviewed_motion_bundle_contract(
            expected_project_id,
            documents[DOCUMENT_NAMES[0]],
            documents[DOCUMENT_NAMES[1]],
            documents[DOCUMENT_NAMES[2]],
            documents[DOCUMENT_NAMES[3]],
            documents[DOCUMENT_NAMES[4]],
            mesh_bundle,
            base_instance,
            target_profile,
        )
        if contract.document_bytes != raw:
            raise ReviewedMotionBundleIntegrityError(
                "Reviewed-motion bytes are not strict canonical snapshots"
            )
        if contract.project_id != expected_project_id \
                or contract.motion_instance_v2_sha256 != \
                expected_motion_instance_v2_sha256 \
                or contract.bundle_sha256 != expected_bundle_sha256:
            raise ReviewedMotionBundleIntegrityError(
                "Reviewed-motion bundle differs from its explicit address"
            )
        if require_address_path:
            _require_address(snapshot.path, contract)
        return VerifiedReviewedMotionBundle(
            snapshot.path, contract.project_id, contract.clip_id,
            contract.foot_lock_candidates_sha256,
            contract.depth_order_candidates_sha256,
            contract.motion_policy_decision_sha256,
            contract.reviewed_motion_policy_sha256,
            contract.motion_instance_v2_sha256,
            contract.run_sha256, contract.bundle_sha256,
            tuple((name, raw[name]) for name in DOCUMENT_NAMES),
        )
    except ReviewedMotionBundleIntegrityError:
        raise
    except (
        ReviewedMotionBundleContractError, ReviewedMotionBundleUpstreamError,
        SafeInputFileError, KeyError, OverflowError, TypeError, ValueError,
    ) as exc:
        raise ReviewedMotionBundleIntegrityError(
            f"Reviewed-motion integrity verification failed: {exc}"
        ) from exc


def _exact_items(items) -> dict[str, bytes]:
    if type(items) is not tuple or len(items) != len(DOCUMENT_NAMES):
        raise ReviewedMotionBundleIntegrityError(
            "Reviewed-motion snapshot inventory is invalid"
        )
    result: dict[str, bytes] = {}
    total = 0
    for index, item in enumerate(items):
        if type(item) is not tuple or len(item) != 2 \
                or item[0] != DOCUMENT_NAMES[index] \
                or not isinstance(item[1], bytes):
            raise ReviewedMotionBundleIntegrityError(
                "Reviewed-motion snapshot order or type is invalid"
            )
        total += len(item[1])
        if len(item[1]) > DOCUMENT_LIMITS[index]:
            raise ReviewedMotionBundleIntegrityError(
                f"{item[0]} exceeds its snapshot byte limit"
            )
        if total > MAX_TOTAL_DOCUMENT_BYTES:
            raise ReviewedMotionBundleIntegrityError(
                "Reviewed-motion snapshot exceeds its total byte limit"
            )
        result[item[0]] = item[1]
    return result


def _require_address(path: Path, contract) -> None:
    # This pure replay boundary validates the canonical address suffix only.
    # The exact reader separately resolves and contains the path under state_root;
    # staging verification intentionally opts out of this suffix check.
    parts = (
        path.name,
        path.parent.name,
        path.parent.parent.name,
        path.parent.parent.parent.name,
        path.parent.parent.parent.parent.name,
    )
    expected = (
        contract.bundle_sha256,
        contract.motion_instance_v2_sha256,
        NAMESPACE,
        contract.project_id,
        "builds",
    )
    if parts != expected:
        raise ReviewedMotionBundleIntegrityError(
            "Reviewed-motion content-address path is invalid"
        )
