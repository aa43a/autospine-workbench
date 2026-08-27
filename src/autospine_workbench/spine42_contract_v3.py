"""Pinned pure input contract for the MotionInstance v3 Spine 4.2 adapter."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import re
from typing import Any

from .motion_instance_v3_bundle_contract import (
    MotionInstanceV3BundleContractError,
    build_motion_instance_v3_bundle_contract,
)
from .motion_instance_v3_validation import (
    MotionInstanceV3ValidationError,
    require_motion_instance_v3,
)
from .motion_target_validation import (
    MotionTargetValidationError,
    require_motion_target_profile,
)
from .resolved_project import canonical_sha256
from .reviewed_motion_bundle_integrity import VerifiedReviewedMotionBundle
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
ADAPTER_VERSION = "3.0.0"
PROFILE_HASH_DOMAIN = "autospine-spine42-json-adapter-v3-profile/v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PROFILE = {
    "adapter": {"id": ADAPTER_ID, "version": ADAPTER_VERSION},
    "skeleton_format": "json",
    "spine_major_minor": SPINE_MAJOR_MINOR,
    "skeleton_json_version": SPINE_JSON_VERSION,
    "runtime": {
        "package": SPINE_RUNTIME_PACKAGE,
        "version": SPINE_RUNTIME_VERSION,
    },
    "capabilities": {
        "motion_instance_v3": {
            "rotation": "setup-local-degree-linear",
            "root_translation": "setup-local-pixel-linear",
            "markers": "contact-boundary-events",
            "draw_order": "full-back-to-front-stepped",
        },
        "rig_ir_attachments": ["region", "weighted_mesh"],
    },
    "unsupported_feature_policy": "fail",
}


class Spine42ContractV3Error(ValueError):
    """Raised when an input exceeds the pinned v3 adapter capability."""


@dataclass(frozen=True, slots=True)
class Spine42V3InputBindings:
    """Exact identities admitted to one pure adapter invocation."""

    adapter_profile_sha256: str
    rig_sha256: str
    motion_instance_v3_sha256: str
    motion_instance_v3_bundle_sha256: str
    motion_instance_v3_profile_sha256: str
    target_profile_sha256: str


def spine42_target_profile_v3() -> dict[str, Any]:
    """Return a detached copy of the explicit adapter v3 capability profile."""

    return json.loads(json.dumps(
        _PROFILE, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))


def spine42_target_profile_v3_sha256() -> str:
    """Return the domain-separated identity of the pinned adapter profile."""

    return canonical_sha256({
        "domain": PROFILE_HASH_DOMAIN,
        "profile": _PROFILE,
    })


def require_spine42_inputs_v3(
    rig: Mapping[str, Any],
    *,
    motion_instance_v3: Mapping[str, Any],
    admission: Mapping[str, Any],
    reviewed_bundle: VerifiedReviewedMotionBundle,
    motion_instance_v3_bundle_sha256: str,
    target_profile: Mapping[str, Any],
    adapter_profile: Mapping[str, Any] | None = None,
) -> Spine42V3InputBindings:
    """Replay exact P10.6a/P9 inputs and reject every unpinned capability."""

    try:
        selected_profile = (
            spine42_target_profile_v3()
            if adapter_profile is None else _json_object_copy(
                adapter_profile, "Spine 4.2 adapter v3 profile"
            )
        )
        if selected_profile != _PROFILE:
            raise Spine42ContractV3Error(
                "Spine 4.2 adapter v3 profile is unknown or unsupported"
            )
        if not isinstance(motion_instance_v3_bundle_sha256, str) \
                or not _SHA256.fullmatch(
                    motion_instance_v3_bundle_sha256
                ):
            raise Spine42ContractV3Error(
                "MotionInstance v3 bundle SHA-256 is invalid"
            )
        require_spine42_rig(rig)
        require_motion_target_profile(target_profile)
        require_motion_instance_v3(
            motion_instance_v3,
            admission=admission,
            reviewed_bundle=reviewed_bundle,
        )
        rig_sha = canonical_sha256(rig)
        instance_sha = canonical_sha256(motion_instance_v3)
        target_sha = canonical_sha256(target_profile)
        source = _mapping(
            motion_instance_v3.get("source"), "MotionInstance v3 source"
        )
        target_source = _mapping(
            target_profile.get("source"), "target source"
        )
        target_p3 = _mapping(target_source.get("p3"), "target P3 source")
        p9_motion = reviewed_bundle.document("motion-instance-v2.json")
        p9_source = _mapping(p9_motion.get("source"), "P9 motion source")
        _require_cross_bindings(
            rig, target_profile, reviewed_bundle, source, target_p3,
            p9_source, rig_sha, target_sha,
        )
        contract = build_motion_instance_v3_bundle_contract(
            reviewed_bundle.project_id,
            _json_object_copy(admission, "P10.6a admission"),
            _json_object_copy(motion_instance_v3, "MotionInstance v3"),
            reviewed_bundle,
        )
        if contract.motion_instance_v3_sha256 != instance_sha \
                or contract.bundle_sha256 \
                != motion_instance_v3_bundle_sha256:
            raise Spine42ContractV3Error(
                "MotionInstance v3 differs from its exact bundle address"
            )
        return Spine42V3InputBindings(
            spine42_target_profile_v3_sha256(), rig_sha, instance_sha,
            contract.bundle_sha256,
            source["motion_instance_v3_profile_sha256"], target_sha,
        )
    except Spine42ContractV3Error:
        raise
    except (
        MotionInstanceV3BundleContractError,
        MotionInstanceV3ValidationError,
        MotionTargetValidationError,
        Spine42RigValidationError,
        AttributeError,
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
    ) as exc:
        raise Spine42ContractV3Error(
            f"Spine 4.2 adapter v3 input validation failed: {exc}"
        ) from exc


def _require_cross_bindings(
    rig, target, reviewed, source, target_p3, p9_source, rig_sha, target_sha,
) -> None:
    if source.get("rig_ir_sha256") != rig_sha \
            or target_p3.get("rig_sha256") != rig_sha \
            or p9_source.get("p3_rig_sha256") != rig_sha:
        raise Spine42ContractV3Error(
            "RigIR differs from its MotionInstance v3, target, or P9 binding"
        )
    if source.get("target_profile_sha256") != target_sha \
            or p9_source.get("target_profile_sha256") != target_sha:
        raise Spine42ContractV3Error(
            "Target profile differs from its MotionInstance v3 or P9 binding"
        )
    if target_p3.get("bundle_sha256") \
            != p9_source.get("p3_bundle_sha256"):
        raise Spine42ContractV3Error(
            "Target profile and P9 bind different P3 bundles"
        )
    if target.get("project_id") != reviewed.project_id:
        raise Spine42ContractV3Error(
            "Target profile and reviewed P9 project differ"
        )
    if target.get("target_space", {}).get("canvas") != rig.get("canvas"):
        raise Spine42ContractV3Error(
            "Target profile canvas differs from P3 RigIR"
        )


def _json_object_copy(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise Spine42ContractV3Error(f"{label} must be an object")
    try:
        result = json.loads(json.dumps(
            dict(value), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ))
    except (OverflowError, TypeError, ValueError) as exc:
        raise Spine42ContractV3Error(f"{label} is not strict JSON") from exc
    if type(result) is not dict:
        raise Spine42ContractV3Error(f"{label} must be an exact JSON object")
    return result


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise Spine42ContractV3Error(f"{label} must be an object")
    return value


__all__ = [
    "ADAPTER_ID", "ADAPTER_VERSION", "Spine42ContractV3Error",
    "Spine42V3InputBindings", "require_spine42_inputs_v3",
    "spine42_target_profile_v3", "spine42_target_profile_v3_sha256",
]
