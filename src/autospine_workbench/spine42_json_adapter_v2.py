"""Policy-aware MotionInstance v2 to Spine 4.2 JSON conversion."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .resolved_project import canonical_sha256
from .spine42_contract import Spine42ContractError, canonical_spine42_json
from .spine42_contract_v2 import (
    Spine42ContractV2Error,
    require_spine42_inputs_v2,
    spine42_target_profile_v2,
)
from .spine42_json_adapter import build_spine42_json
from .spine42_timeline_projection import (
    Spine42TimelineProjectionError,
    project_spine42_motion,
)


def build_spine42_json_v2(
    rig: Mapping[str, Any],
    *,
    motion_instance: Mapping[str, Any],
    target_profile: Mapping[str, Any],
) -> dict[str, Any]:
    """Build one deterministic policy-aware Spine 4.2 JSON document."""

    require_spine42_inputs_v2(
        rig,
        motion_instance=motion_instance,
        target_profile=target_profile,
    )
    try:
        document = build_spine42_json(rig)
    except Spine42ContractError as exc:
        raise Spine42ContractV2Error(
            f"Spine 4.2 adapter v2 setup projection failed: {exc}"
        ) from exc
    try:
        events, animation = project_spine42_motion(
            motion_instance, document["slots"]
        )
    except Spine42TimelineProjectionError as exc:
        raise Spine42ContractV2Error(str(exc)) from exc
    document["events"] = events
    document["animations"] = {motion_instance["clip_id"]: animation}
    document["skeleton"]["hash"] = canonical_sha256({
        "adapter_profile": spine42_target_profile_v2(),
        "rig_sha256": canonical_sha256(rig),
        "motion_instance_v2_sha256": canonical_sha256(motion_instance),
        "target_profile_sha256": canonical_sha256(target_profile),
    })
    try:
        return json.loads(canonical_spine42_json(document))
    except (TypeError, ValueError) as exc:
        raise Spine42ContractV2Error(
            f"Projected Spine 4.2 adapter v2 document is invalid: {exc}"
        ) from exc


def build_spine42_json_bytes_v2(
    rig: Mapping[str, Any],
    *,
    motion_instance: Mapping[str, Any],
    target_profile: Mapping[str, Any],
) -> bytes:
    """Build and canonically serialize one adapter v2 result."""

    return canonical_spine42_json(build_spine42_json_v2(
        rig,
        motion_instance=motion_instance,
        target_profile=target_profile,
    ))
