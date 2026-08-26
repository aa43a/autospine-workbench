"""Pinned input contract for the policy-aware Spine 4.2 adapter v2."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .motion_instance_v2_validation import (
    MotionInstanceV2ValidationError,
    require_motion_instance_v2,
)
from .motion_target_validation import (
    MotionTargetValidationError,
    require_motion_target_profile,
)
from .resolved_project import canonical_sha256
from .spine42_contract import (
    SPINE_JSON_VERSION,
    SPINE_MAJOR_MINOR,
    SPINE_RUNTIME_PACKAGE,
    SPINE_RUNTIME_VERSION,
)
from .spine42_rig_validation import (
    Spine42RigValidationError,
    require_spine42_rig,
)


ADAPTER_ID = "autospine-spine42-json-adapter"
ADAPTER_VERSION = "2.0.0"


class Spine42ContractV2Error(ValueError):
    """Raised when reviewed motion cannot enter the pinned v2 adapter."""


def spine42_target_profile_v2() -> dict[str, Any]:
    """Return a fresh copy of the exact policy-aware adapter profile."""

    return {
        "adapter": {"id": ADAPTER_ID, "version": ADAPTER_VERSION},
        "skeleton_format": "json",
        "spine_major_minor": SPINE_MAJOR_MINOR,
        "skeleton_json_version": SPINE_JSON_VERSION,
        "runtime": {
            "package": SPINE_RUNTIME_PACKAGE,
            "version": SPINE_RUNTIME_VERSION,
        },
    }


def require_spine42_inputs_v2(
    rig: Mapping[str, Any],
    *,
    motion_instance: Mapping[str, Any],
    target_profile: Mapping[str, Any],
) -> None:
    """Fail closed unless the exact P3, P5 target, and v2 instance agree."""

    try:
        require_spine42_rig(rig)
        require_motion_target_profile(target_profile)
        require_motion_instance_v2(
            motion_instance,
            target_profile=target_profile,
        )
        rig_sha = canonical_sha256(rig)
        target_p3 = _mapping(
            _mapping(target_profile.get("source"), "target source").get("p3"),
            "target P3 source",
        )
        instance_source = _mapping(
            motion_instance.get("source"), "MotionInstance v2 source"
        )
        if target_p3.get("rig_sha256") != rig_sha:
            raise Spine42ContractV2Error(
                "Target profile is stale for this P3 RigIR"
            )
        if instance_source.get("p3_rig_sha256") != rig_sha:
            raise Spine42ContractV2Error(
                "MotionInstance v2 is stale for this P3 RigIR"
            )
        if instance_source.get("p3_bundle_sha256") != target_p3.get("bundle_sha256"):
            raise Spine42ContractV2Error(
                "MotionInstance v2 and target P3 bundle bindings differ"
            )
        if target_profile.get("target_space", {}).get("canvas") != rig["canvas"]:
            raise Spine42ContractV2Error(
                "Target profile canvas differs from P3 RigIR"
            )
    except Spine42ContractV2Error:
        raise
    except (
        MotionInstanceV2ValidationError,
        MotionTargetValidationError,
        Spine42RigValidationError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise Spine42ContractV2Error(
            f"Spine 4.2 adapter v2 input validation failed: {exc}"
        ) from exc


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise Spine42ContractV2Error(f"{label} must be an object")
    return value
