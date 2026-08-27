"""Pure MotionInstance v3 to Spine 4.2 JSON projection."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .resolved_project import canonical_sha256
from .reviewed_motion_bundle_integrity import VerifiedReviewedMotionBundle
from .spine42_contract import (
    Spine42ContractError,
    canonical_spine42_json,
)
from .spine42_contract_v3 import (
    Spine42ContractV3Error,
    Spine42V3InputBindings,
    require_spine42_inputs_v3,
    spine42_target_profile_v3,
    spine42_target_profile_v3_sha256,
)
from .spine42_json_adapter import build_spine42_json
from .spine42_timeline_projection import (
    Spine42TimelineProjectionError,
    project_spine42_motion,
)


def build_spine42_json_v3(
    rig: Mapping[str, Any],
    *,
    motion_instance_v3: Mapping[str, Any],
    admission: Mapping[str, Any],
    reviewed_bundle: VerifiedReviewedMotionBundle,
    motion_instance_v3_bundle_sha256: str,
    target_profile: Mapping[str, Any],
    adapter_profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one deterministic Spine 4.2 document from exact v3 sources."""

    rig_document = _copy(rig, "P3 RigIR")
    instance_document = _copy(
        motion_instance_v3, "MotionInstance v3"
    )
    admission_document = _copy(admission, "P10.6a admission")
    target_document = _copy(target_profile, "P5 target profile")
    selected_profile = (
        None if adapter_profile is None
        else _copy(adapter_profile, "Spine 4.2 adapter v3 profile")
    )
    bindings = require_spine42_inputs_v3(
        rig_document,
        motion_instance_v3=instance_document,
        admission=admission_document,
        reviewed_bundle=reviewed_bundle,
        motion_instance_v3_bundle_sha256=
            motion_instance_v3_bundle_sha256,
        target_profile=target_document,
        adapter_profile=selected_profile,
    )
    try:
        document = build_spine42_json(rig_document)
        events, animation = project_spine42_motion(
            instance_document, document["slots"]
        )
        document["events"] = events
        document["animations"] = {
            instance_document["clip_id"]: animation
        }
        document["skeleton"]["hash"] = spine42_skeleton_hash_v3(
            bindings
        )
        return json.loads(canonical_spine42_json(document))
    except Spine42ContractV3Error:
        raise
    except (
        Spine42ContractError,
        Spine42TimelineProjectionError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise Spine42ContractV3Error(
            f"Spine 4.2 adapter v3 projection failed: {exc}"
        ) from exc


def build_spine42_json_bytes_v3(
    rig: Mapping[str, Any],
    *,
    motion_instance_v3: Mapping[str, Any],
    admission: Mapping[str, Any],
    reviewed_bundle: VerifiedReviewedMotionBundle,
    motion_instance_v3_bundle_sha256: str,
    target_profile: Mapping[str, Any],
    adapter_profile: Mapping[str, Any] | None = None,
) -> bytes:
    """Build and canonically serialize one adapter v3 result."""

    return canonical_spine42_json(build_spine42_json_v3(
        rig,
        motion_instance_v3=motion_instance_v3,
        admission=admission,
        reviewed_bundle=reviewed_bundle,
        motion_instance_v3_bundle_sha256=
            motion_instance_v3_bundle_sha256,
        target_profile=target_profile,
        adapter_profile=adapter_profile,
    ))


def spine42_skeleton_hash_v3(bindings: Spine42V3InputBindings) -> str:
    """Bind the exported skeleton identity to every exact adapter source."""

    if type(bindings) is not Spine42V3InputBindings:
        raise Spine42ContractV3Error(
            "Spine 4.2 adapter v3 bindings type is invalid"
        )
    expected_profile_sha = spine42_target_profile_v3_sha256()
    if bindings.adapter_profile_sha256 != expected_profile_sha:
        raise Spine42ContractV3Error(
            "Spine 4.2 adapter v3 profile identity differs"
        )
    return canonical_sha256({
        "adapter_profile": spine42_target_profile_v3(),
        "adapter_profile_sha256": bindings.adapter_profile_sha256,
        "rig_sha256": bindings.rig_sha256,
        "motion_instance_v3_sha256":
            bindings.motion_instance_v3_sha256,
        "motion_instance_v3_bundle_sha256":
            bindings.motion_instance_v3_bundle_sha256,
        "motion_instance_v3_profile_sha256":
            bindings.motion_instance_v3_profile_sha256,
        "target_profile_sha256": bindings.target_profile_sha256,
    })


def _copy(value: Mapping[str, Any], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise Spine42ContractV3Error(f"{label} must be an object")
    try:
        result = json.loads(canonical_spine42_json(value))
    except Spine42ContractError as exc:
        raise Spine42ContractV3Error(
            f"{label} is not strict canonical JSON: {exc}"
        ) from exc
    if type(result) is not dict:
        raise Spine42ContractV3Error(f"{label} must be an exact JSON object")
    return result


__all__ = [
    "build_spine42_json_bytes_v3", "build_spine42_json_v3",
    "spine42_skeleton_hash_v3",
]
