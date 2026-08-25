"""Pinned, loss-intolerant input contract for the Spine 4.2 JSON adapter."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from typing import Any

from .motion_instance_validation import (
    MotionInstanceValidationError,
    require_motion_instance,
)
from .motion_target_validation import (
    MotionTargetValidationError,
    require_motion_target_profile,
)
from .resolved_project import canonical_sha256
from .spine42_rig_validation import (
    Spine42RigValidationError,
    require_spine42_rig,
)


SPINE_MAJOR_MINOR = "4.2"
SPINE_JSON_VERSION = "4.2"
SPINE_RUNTIME_PACKAGE = "@esotericsoftware/spine-player"
SPINE_RUNTIME_VERSION = "4.2.119"
ADAPTER_ID = "autospine-spine42-json-adapter"
ADAPTER_VERSION = "1.0.0"

class Spine42ContractError(ValueError):
    """Raised when a source cannot be represented by the pinned profile."""


def spine42_target_profile() -> dict[str, Any]:
    """Return a fresh copy of the exact runtime/export compatibility target."""

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


def require_spine42_inputs(
    rig: Mapping[str, Any],
    *,
    motion_instance: Mapping[str, Any] | None = None,
    target_profile: Mapping[str, Any] | None = None,
) -> None:
    """Fail closed unless exact P3 and optional paired P5 inputs are safe."""

    try:
        require_spine42_rig(rig)
        paired = motion_instance is not None or target_profile is not None
        if paired and (motion_instance is None or target_profile is None):
            raise Spine42ContractError(
                "MotionInstance and target profile must be supplied together"
            )
        if motion_instance is not None and target_profile is not None:
            require_motion_target_profile(target_profile)
            require_motion_instance(motion_instance, target_profile=target_profile)
            p3 = _mapping(target_profile.get("source"), "target source").get("p3")
            p3 = _mapping(p3, "target P3 source")
            if p3.get("rig_sha256") != canonical_sha256(rig):
                raise Spine42ContractError("Target profile is stale for this P3 RigIR")
            if target_profile.get("target_space", {}).get("canvas") != rig["canvas"]:
                raise Spine42ContractError("Target profile canvas differs from P3 RigIR")
    except Spine42ContractError:
        raise
    except (
        MotionInstanceValidationError,
        MotionTargetValidationError,
        Spine42RigValidationError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise Spine42ContractError(f"Spine 4.2 input validation failed: {exc}") from exc


def canonical_spine42_json(document: Mapping[str, Any]) -> bytes:
    """Serialize one adapter result as deterministic UTF-8 canonical JSON."""

    if not isinstance(document, Mapping):
        raise Spine42ContractError("Spine JSON document must be an object")
    try:
        return json.dumps(
            dict(document), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise Spine42ContractError("Spine JSON is not finite canonical JSON") from exc


def spine42_json_sha256(document: Mapping[str, Any]) -> str:
    """Return the deterministic content address of an adapter result."""

    return hashlib.sha256(canonical_spine42_json(document)).hexdigest()


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise Spine42ContractError(f"{label} must be an object")
    return value
