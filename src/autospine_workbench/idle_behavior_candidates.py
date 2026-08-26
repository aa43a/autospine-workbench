"""Pure in-memory P10.0 idle candidate and observability compiler."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .idle_behavior_candidate_validation import (
    FORMAT,
    FORMAT_VERSION,
    GENERATOR,
    SEMANTICS,
    TARGET_CAPABILITIES,
    IdleBehaviorCandidateValidationError,
    idle_behavior_candidates_sha256,
    require_idle_behavior_candidates,
)
from .idle_behavior_inputs import (
    IdleBehaviorInputError,
    require_idle_behavior_inputs,
)
from .idle_behavior_inventory import (
    IdleBehaviorInventoryError,
    derive_idle_behavior_inventory,
)
from .idle_behavior_rules import (
    IdleBehaviorRuleError,
    classify_idle_behavior_features,
)
from .mesh_bundle_integrity import VerifiedMeshBundle
from .motion_retarget_bundle_integrity import VerifiedMotionRetargetBundle
from .reviewed_motion_bundle_contract import ReviewedMotionBundleContract


class IdleBehaviorCandidateError(ValueError):
    """Raised when exact evidence cannot produce a candidate-only report."""


@dataclass(frozen=True, slots=True)
class IdleBehaviorCandidates:
    """Frozen canonical value object; accessors return isolated values."""

    _canonical_json: str

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


def compile_idle_behavior_candidates(
    layer_manifest: Mapping[str, Any],
    mesh_bundle: VerifiedMeshBundle,
    retarget_bundle: VerifiedMotionRetargetBundle,
    reviewed_bundle: ReviewedMotionBundleContract,
) -> IdleBehaviorCandidates:
    """Classify setup evidence; never emit a decision, graph, or timeline."""

    try:
        inputs = require_idle_behavior_inputs(
            layer_manifest, mesh_bundle, retarget_bundle, reviewed_bundle
        )
        inventory = derive_idle_behavior_inventory(
            inputs.manifest, inputs.rig, inputs.target_profile,
            inputs.motion_instance_v2,
        )
        source = inputs.source
        features = classify_idle_behavior_features(
            inventory,
            motion_instance_v2_sha256=source["p9"][
                "motion_instance_v2_sha256"
            ],
            target_profile_sha256=source["p5"]["target_profile_sha256"],
        )
        counts = {
            name: sum(row["availability"] == name for row in features)
            for name in ("candidate", "unobservable", "unsupported")
        }
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "project_id": inputs.project_id,
            "clip_id": inputs.clip_id,
            "source": source,
            "timing": inputs.timing,
            "target_capabilities": _copy(TARGET_CAPABILITIES),
            "generator": _copy(GENERATOR),
            "semantics": _copy(SEMANTICS),
            "features": features,
            "summary": {
                "status": "candidate_only",
                "feature_count": len(features),
                "candidate_count": counts["candidate"],
                "unobservable_count": counts["unobservable"],
                "unsupported_count": counts["unsupported"],
            },
        }
        require_idle_behavior_candidates(document)
        value = IdleBehaviorCandidates(_canonical(document))
        if value.sha256 != idle_behavior_candidates_sha256(value.document):
            raise IdleBehaviorCandidateError(
                "Idle behavior candidate canonical identity is inconsistent"
            )
        return value
    except IdleBehaviorCandidateError:
        raise
    except (
        IdleBehaviorCandidateValidationError, IdleBehaviorInputError,
        IdleBehaviorInventoryError, IdleBehaviorRuleError,
        KeyError, OverflowError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise IdleBehaviorCandidateError(
            f"Idle behavior candidate compilation failed: {exc}"
        ) from exc


def _copy(value: Any) -> Any:
    return json.loads(_canonical(value))


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
