"""Pure reviewed-policy overlay compilation for MotionInstance v2."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .motion_instance_v2_overlay import overlay_motion_tracks
from .motion_instance_v2_sampling import MotionInstanceV2SamplingError
from .motion_instance_v2_validation import (
    FORMAT,
    FORMAT_VERSION,
    MotionInstanceV2ValidationError,
    motion_instance_v2_sha256,
    require_motion_instance_v2,
)
from .motion_instance_validation import (
    MotionInstanceValidationError,
    require_motion_instance,
)
from .motion_target_validation import (
    MotionTargetValidationError,
    require_motion_target_profile,
)
from .resolved_project import canonical_sha256
from .reviewed_motion_policy_validation import (
    ReviewedMotionPolicyValidationError,
    require_reviewed_motion_policy,
    reviewed_motion_policy_sha256,
)


class MotionInstanceV2CompilerError(ValueError):
    """Raised when exact P5/P9 inputs cannot form a safe v2 overlay."""


@dataclass(frozen=True, slots=True)
class MotionInstanceV2:
    """Frozen canonical v2 value with isolated document access."""

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


def compile_motion_instance_v2(
    base_instance: Mapping[str, Any],
    target_profile: Mapping[str, Any],
    reviewed_policy: Mapping[str, Any],
) -> MotionInstanceV2:
    """Add reviewed root/draw-order policy without mutating source snapshots."""

    try:
        require_motion_instance(base_instance, target_profile=target_profile)
        require_motion_target_profile(target_profile)
        require_reviewed_motion_policy(reviewed_policy)
        _require_shared_chain(base_instance, target_profile, reviewed_policy)
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "clip_id": base_instance["clip_id"],
            "timing": _copy(base_instance["timing"]),
            "source": _source(base_instance, target_profile, reviewed_policy),
            "target_space": {
                **_copy(base_instance["target_space"]),
                "draw_order": "full-back-to-front-stepped",
            },
            "tracks": overlay_motion_tracks(base_instance, reviewed_policy),
            "markers": _copy(base_instance["markers"]),
            "draw_order": _copy(reviewed_policy["slot_order"]),
        }
        require_motion_instance_v2(
            document,
            target_profile=target_profile,
            base_motion_instance=base_instance,
            reviewed_motion_policy=reviewed_policy,
        )
        value = MotionInstanceV2(_canonical(document))
        if value.sha256 != motion_instance_v2_sha256(value.document):
            raise MotionInstanceV2CompilerError(
                "MotionInstance v2 canonical identity is inconsistent"
            )
        return value
    except MotionInstanceV2CompilerError:
        raise
    except (
        KeyError,
        MotionInstanceValidationError,
        MotionInstanceV2SamplingError,
        MotionInstanceV2ValidationError,
        MotionTargetValidationError,
        ReviewedMotionPolicyValidationError,
        TypeError,
        ValueError,
    ) as exc:
        raise MotionInstanceV2CompilerError(
            f"MotionInstance v2 compilation failed: {exc}"
        ) from exc


def _require_shared_chain(base, target, policy) -> None:
    timing = {
        field: policy["timing"][field]
        for field in ("ticks_per_second", "duration_ticks", "loop")
    }
    base_sha, target_sha = canonical_sha256(base), canonical_sha256(target)
    p5, p3 = policy["source"]["p5"], policy["source"]["p3"]
    if base["clip_id"] != policy["clip_id"] or base["timing"] != timing:
        raise MotionInstanceV2CompilerError(
            "Base instance and reviewed policy clip timing differ"
        )
    if base_sha != p5["instance_sha256"]:
        raise MotionInstanceV2CompilerError(
            "Reviewed policy does not bind the exact base instance"
        )
    if target_sha != base["source"]["target_profile_sha256"] \
            or target_sha != p5["target_profile_sha256"]:
        raise MotionInstanceV2CompilerError(
            "Reviewed policy, base instance, and target profile differ"
        )
    if target["source"]["p3"] != p3:
        raise MotionInstanceV2CompilerError(
            "Reviewed policy and target profile P3 chains differ"
        )
    if target["project_id"] != policy["project_id"]:
        raise MotionInstanceV2CompilerError(
            "Reviewed policy and target profile projects differ"
        )


def _source(base, target, policy) -> dict[str, str]:
    p5, p3 = policy["source"]["p5"], policy["source"]["p3"]
    return {
        "base_motion_instance_sha256": canonical_sha256(base),
        "base_retarget_bundle_sha256": p5["bundle_sha256"],
        "target_profile_sha256": canonical_sha256(target),
        "reviewed_motion_policy_sha256": reviewed_motion_policy_sha256(policy),
        "motion_policy_decision_sha256": policy["source"][
            "motion_policy_decision_sha256"
        ],
        "p3_rig_sha256": p3["rig_sha256"],
        "p3_bundle_sha256": p3["bundle_sha256"],
    }


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
