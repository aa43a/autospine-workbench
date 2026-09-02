"""Pure Spine 4.2 projection for reader-issued P10.6b v2 bundles."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .motion_instance_v3_bundle_reader_v2 import (
    VerifiedMotionInstanceV3BundleV2,
)
from .resolved_project import canonical_sha256
from .reviewed_motion_bundle_integrity import VerifiedReviewedMotionBundle
from .spine42_contract import Spine42ContractError, canonical_spine42_json
from .spine42_contract_v3_v2 import (
    Spine42ContractV3V2Error, Spine42V3InputBindingsV2,
    require_spine42_inputs_v3_v2, spine42_source_contract_v3_v2,
    spine42_source_contract_v3_v2_sha256,
    spine42_target_profile_v3_v2, spine42_target_profile_v3_v2_sha256,
)
from .spine42_json_adapter import build_spine42_json
from .spine42_timeline_projection import (
    Spine42TimelineProjectionError, project_spine42_motion,
)


def build_spine42_json_v3_v2(
    rig: Mapping[str, Any], *,
    motion_bundle: VerifiedMotionInstanceV3BundleV2,
    reviewed_bundle: VerifiedReviewedMotionBundle,
    target_profile: Mapping[str, Any],
    adapter_profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project the exact v2-source motion without invoking frozen v1 replay."""

    rig_document = _copy(rig, "P3 RigIR")
    target_document = _copy(target_profile, "P5 target profile")
    selected = None if adapter_profile is None else _copy(
        adapter_profile, "Spine 4.2 v2-source adapter profile",
    )
    bindings = require_spine42_inputs_v3_v2(
        rig_document, motion_bundle=motion_bundle,
        reviewed_bundle=reviewed_bundle, target_profile=target_document,
        adapter_profile=selected,
    )
    instance = motion_bundle.document("motion-instance-v3.json")
    try:
        document = build_spine42_json(rig_document)
        events, animation = project_spine42_motion(
            instance, document["slots"],
        )
        document["events"] = events
        document["animations"] = {instance["clip_id"]: animation}
        document["skeleton"]["hash"] = spine42_skeleton_hash_v3_v2(
            bindings
        )
        return json.loads(canonical_spine42_json(document))
    except Spine42ContractV3V2Error:
        raise
    except (
        KeyError, Spine42ContractError, Spine42TimelineProjectionError,
        TypeError, ValueError,
    ) as exc:
        raise Spine42ContractV3V2Error(
            f"Spine 4.2 v2-source projection failed: {exc}"
        ) from exc


def build_spine42_json_bytes_v3_v2(*args, **kwargs) -> bytes:
    return canonical_spine42_json(build_spine42_json_v3_v2(
        *args, **kwargs,
    ))


def spine42_skeleton_hash_v3_v2(
    bindings: Spine42V3InputBindingsV2,
) -> str:
    if type(bindings) is not Spine42V3InputBindingsV2 \
            or bindings.adapter_profile_sha256 \
                != spine42_target_profile_v3_v2_sha256() \
            or bindings.source_contract_sha256 \
                != spine42_source_contract_v3_v2_sha256():
        raise Spine42ContractV3V2Error(
            "Spine 4.2 v2-source binding profile differs"
        )
    return canonical_sha256({
        "domain": "autospine-spine42-v3-skeleton-source/v2",
        "adapter_profile": spine42_target_profile_v3_v2(),
        "adapter_profile_sha256": bindings.adapter_profile_sha256,
        "source_contract": spine42_source_contract_v3_v2(),
        "source_contract_sha256": bindings.source_contract_sha256,
        "motion_instance_v3_source_sha256":
            bindings.motion_instance_v3_source_sha256,
        "rig_sha256": bindings.rig_sha256,
        "motion_instance_v3_sha256":
            bindings.motion_instance_v3_sha256,
        "motion_instance_v3_bundle_sha256":
            bindings.motion_instance_v3_bundle_sha256,
        "motion_instance_v3_profile_sha256":
            bindings.motion_instance_v3_profile_sha256,
        "target_profile_sha256": bindings.target_profile_sha256,
    })


def _copy(value, label):
    if not isinstance(value, Mapping):
        raise Spine42ContractV3V2Error(f"{label} must be an object")
    try:
        result = json.loads(canonical_spine42_json(value))
    except Spine42ContractError as exc:
        raise Spine42ContractV3V2Error(
            f"{label} is not strict canonical JSON"
        ) from exc
    if type(result) is not dict:
        raise Spine42ContractV3V2Error(f"{label} must be an object")
    return result


__all__ = [
    "build_spine42_json_bytes_v3_v2", "build_spine42_json_v3_v2",
    "spine42_skeleton_hash_v3_v2",
]
