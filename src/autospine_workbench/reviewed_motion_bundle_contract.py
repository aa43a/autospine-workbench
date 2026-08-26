"""Pure immutable six-document contract for reviewed P9 motion."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .depth_order_candidate_validation import (
    DepthOrderCandidateValidationError,
    depth_order_candidates_sha256,
    require_depth_order_candidates,
)
from .foot_lock_candidate_validation import (
    FootLockCandidateValidationError,
    foot_lock_candidates_sha256,
    require_foot_lock_candidates,
)
from .manifest_artifacts import LayerManifestError, require_safe_token
from .mesh_bundle_admission import MeshBundleAdmissionError, require_exact_mesh_bundle
from .mesh_bundle_integrity import VerifiedMeshBundle
from .motion_instance_v2_compiler import (
    MotionInstanceV2CompilerError,
    compile_motion_instance_v2,
)
from .motion_policy_decision_validation import (
    MotionPolicyDecisionValidationError,
    motion_policy_decision_sha256,
    require_motion_policy_decision,
)
from .resolved_project import canonical_sha256
from .reviewed_motion_bundle_run import (
    MAX_RUN_BYTES,
    ReviewedMotionBundleRunError,
    build_reviewed_motion_bundle_run,
)
from .reviewed_motion_policy import (
    ReviewedMotionPolicyError,
    compile_reviewed_motion_policy,
)
from .reviewed_motion_policy_validation import (
    reviewed_motion_policy_sha256,
)


BUNDLE_ADDRESS_DOMAIN = b"autospine-reviewed-motion-bundle-address/v1"
DOCUMENT_NAMES = (
    "foot-lock-candidates.json",
    "depth-order-candidates.json",
    "motion-policy-decision.json",
    "reviewed-motion-policy.json",
    "motion-instance-v2.json",
    "run-manifest.json",
)
MAX_CANDIDATE_BYTES = 64 * 1024 * 1024
MAX_DECISION_BYTES = 64 * 1024 * 1024
MAX_POLICY_BYTES = 64 * 1024 * 1024
MAX_INSTANCE_V2_BYTES = 16 * 1024 * 1024
DOCUMENT_LIMITS = (
    MAX_CANDIDATE_BYTES, MAX_CANDIDATE_BYTES, MAX_DECISION_BYTES,
    MAX_POLICY_BYTES, MAX_INSTANCE_V2_BYTES, MAX_RUN_BYTES,
)
MAX_TOTAL_DOCUMENT_BYTES = 256 * 1024 * 1024


class ReviewedMotionBundleContractError(ValueError):
    """Raised when proposed reviewed-motion documents cannot be reproduced."""


@dataclass(frozen=True, slots=True)
class ReviewedMotionBundleContract:
    """Frozen canonical documents and their exact domain-separated address."""

    project_id: str
    clip_id: str
    foot_lock_candidates_sha256: str
    depth_order_candidates_sha256: str
    motion_policy_decision_sha256: str
    reviewed_motion_policy_sha256: str
    motion_instance_v2_sha256: str
    run_sha256: str
    bundle_sha256: str
    _documents: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def document_bytes(self) -> dict[str, bytes]:
        return dict(self._documents)

    @property
    def inventory(self) -> tuple[str, ...]:
        return tuple(name for name, _data in self._documents)

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


def build_reviewed_motion_bundle_contract(
    project_id: str,
    foot_candidates: Mapping[str, Any],
    depth_candidates: Mapping[str, Any],
    decision: Mapping[str, Any],
    reviewed_policy: Mapping[str, Any],
    motion_instance_v2: Mapping[str, Any],
    mesh_bundle: VerifiedMeshBundle,
    base_motion_instance: Mapping[str, Any],
    target_profile: Mapping[str, Any],
) -> ReviewedMotionBundleContract:
    """Rebuild both derived documents before freezing a six-file snapshot."""

    try:
        project = require_safe_token(project_id, "Project id")
        require_foot_lock_candidates(foot_candidates)
        require_depth_order_candidates(depth_candidates)
        require_motion_policy_decision(
            decision,
            foot_candidates=foot_candidates,
            depth_candidates=depth_candidates,
        )
        require_exact_mesh_bundle(mesh_bundle)
        if mesh_bundle.project_id != project:
            raise ReviewedMotionBundleContractError(
                "Reviewed-motion project differs from exact P3 bundle"
            )
        compiled_policy = compile_reviewed_motion_policy(
            decision, foot_candidates, depth_candidates, mesh_bundle
        )
        policy_bytes = _document(reviewed_policy, DOCUMENT_NAMES[3], 3)
        if compiled_policy.canonical_bytes != policy_bytes:
            raise ReviewedMotionBundleContractError(
                "Reviewed policy differs from its exact compilation"
            )
        compiled_v2 = compile_motion_instance_v2(
            base_motion_instance, target_profile, reviewed_policy
        )
        v2_bytes = _document(motion_instance_v2, DOCUMENT_NAMES[4], 4)
        if compiled_v2.canonical_bytes != v2_bytes:
            raise ReviewedMotionBundleContractError(
                "MotionInstance v2 differs from its exact compilation"
            )
        if decision.get("project_id") != project \
                or decision.get("clip_id") != compiled_v2.document["clip_id"]:
            raise ReviewedMotionBundleContractError(
                "Reviewed-motion project or clip binding differs"
            )
        initial = tuple(
            _document(value, DOCUMENT_NAMES[index], index)
            for index, value in enumerate((foot_candidates, depth_candidates, decision))
        )
        foot_sha = foot_lock_candidates_sha256(foot_candidates)
        depth_sha = depth_order_candidates_sha256(depth_candidates)
        decision_sha = motion_policy_decision_sha256(
            decision,
            foot_candidates=foot_candidates,
            depth_candidates=depth_candidates,
        )
        run = build_reviewed_motion_bundle_run(
            project, decision["clip_id"],
            p3={"rig_sha256": mesh_bundle.rig_sha256,
                "bundle_sha256": mesh_bundle.bundle_sha256},
            p5={
                "instance_sha256": canonical_sha256(base_motion_instance),
                "bundle_sha256": reviewed_policy["source"]["p5"]["bundle_sha256"],
                "target_profile_sha256": canonical_sha256(target_profile),
            },
            foot_lock_candidates_sha256=foot_sha,
            depth_order_candidates_sha256=depth_sha,
            motion_policy_decision_sha256=decision_sha,
            reviewed_motion_policy_sha256=reviewed_motion_policy_sha256(
                reviewed_policy
            ),
            motion_instance_v2_sha256=compiled_v2.sha256,
        )
        items = _require_items(tuple(zip(
            DOCUMENT_NAMES,
            (*initial, policy_bytes, v2_bytes, run.canonical_bytes),
            strict=True,
        )))
        bundle_sha = reviewed_motion_bundle_address_sha256(
            project, compiled_v2.sha256, items
        )
        return ReviewedMotionBundleContract(
            project, decision["clip_id"], foot_sha, depth_sha, decision_sha,
            compiled_policy.sha256, compiled_v2.sha256, run.sha256,
            bundle_sha, items,
        )
    except ReviewedMotionBundleContractError:
        raise
    except (
        DepthOrderCandidateValidationError, FootLockCandidateValidationError,
        LayerManifestError, MeshBundleAdmissionError,
        MotionInstanceV2CompilerError, MotionPolicyDecisionValidationError,
        ReviewedMotionBundleRunError, ReviewedMotionPolicyError,
        KeyError, OverflowError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise ReviewedMotionBundleContractError(
            f"Reviewed-motion bundle contract failed: {exc}"
        ) from exc


def reviewed_motion_bundle_address_sha256(
    project_id: str,
    motion_instance_v2_sha256: str,
    document_items: tuple[tuple[str, bytes], ...],
) -> str:
    """Hash project, v2 identity, and all ordered filename/byte frames."""

    try:
        project = require_safe_token(project_id, "Project id")
        if not isinstance(motion_instance_v2_sha256, str) \
                or len(motion_instance_v2_sha256) != 64 \
                or any(char not in "0123456789abcdef"
                       for char in motion_instance_v2_sha256):
            raise ReviewedMotionBundleContractError(
                "MotionInstance v2 address is invalid"
            )
        items = _require_items(document_items)
        if _sha(items[4][1]) != motion_instance_v2_sha256:
            raise ReviewedMotionBundleContractError(
                "MotionInstance v2 bytes differ from their address"
            )
        digest = hashlib.sha256()
        _feed(digest, BUNDLE_ADDRESS_DOMAIN)
        _feed(digest, project.encode("utf-8"))
        _feed(digest, motion_instance_v2_sha256.encode("ascii"))
        digest.update(len(items).to_bytes(4, "big"))
        for name, data in items:
            _feed(digest, name.encode("ascii"))
            _feed(digest, data)
        return digest.hexdigest()
    except ReviewedMotionBundleContractError:
        raise
    except (LayerManifestError, OverflowError, TypeError, ValueError) as exc:
        raise ReviewedMotionBundleContractError(
            "Reviewed-motion bundle address inputs are invalid"
        ) from exc


def _document(value: Mapping[str, Any], label: str, index: int) -> bytes:
    if not isinstance(value, Mapping):
        raise ReviewedMotionBundleContractError(f"{label} must be an object")
    data = _canonical(value)
    if len(data) > DOCUMENT_LIMITS[index]:
        raise ReviewedMotionBundleContractError(f"{label} exceeds its byte limit")
    return data


def _require_items(value) -> tuple[tuple[str, bytes], ...]:
    if type(value) is not tuple or len(value) != len(DOCUMENT_NAMES):
        raise ReviewedMotionBundleContractError("Reviewed-motion inventory is invalid")
    result, total = [], 0
    for index, item in enumerate(value):
        if type(item) is not tuple or len(item) != 2 \
                or item[0] != DOCUMENT_NAMES[index] or not isinstance(item[1], bytes):
            raise ReviewedMotionBundleContractError(
                "Reviewed-motion inventory order or type is invalid"
            )
        total += len(item[1])
        if len(item[1]) > DOCUMENT_LIMITS[index]:
            raise ReviewedMotionBundleContractError(
                f"{item[0]} exceeds its byte limit"
            )
        result.append(item)
    if total > MAX_TOTAL_DOCUMENT_BYTES:
        raise ReviewedMotionBundleContractError(
            "Reviewed-motion bundle exceeds its total byte limit"
        )
    return tuple(result)


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _feed(digest, value: bytes) -> None:
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
