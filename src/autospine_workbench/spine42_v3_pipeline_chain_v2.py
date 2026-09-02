"""Pure P10.6b v2 to P9/P5/P3 source-chain checks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .resolved_project import canonical_sha256


class Spine42V3PipelineChainV2Error(ValueError):
    pass


def require_exact_spine42_v3_chain_v2(
    project, v3_sha, v3_bundle_sha, v3, v3_run, reviewed, p9_run,
    motion_v2, p3, p5, retarget, mesh,
) -> None:
    """Require one exact v2-source project/clip/address chain."""

    instance = v3.document("motion-instance-v3.json")
    admission = v3.document(
        "body-sway-motion-consumer-admission-v2.json"
    )
    p9_address = instance["source"]["p9"]
    expected_p3 = require_object(p9_run["inputs"]["p3"], "P9 P3 source")
    target = retarget.target_profile
    target_sha = canonical_sha256(target)
    if v3.project_id != project or reviewed.project_id != project \
            or retarget.project_id != project or mesh.project_id != project \
            or v3.motion_instance_v3_sha256 != v3_sha \
            or v3.bundle_sha256 != v3_bundle_sha \
            or v3_run.get("format_version") != 2 \
            or v3_run.get("project_id") != project \
            or v3_run.get("clip_id") != v3.clip_id \
            or v3_run.get("outputs", {}).get(
                "motion_instance_v3_sha256"
            ) != v3_sha \
            or instance.get("clip_id") != v3.clip_id \
            or admission.get("project_id") != project \
            or admission.get("clip_id") != v3.clip_id \
            or reviewed.clip_id != v3.clip_id \
            or p9_run.get("clip_id") != v3.clip_id \
            or motion_v2.get("clip_id") != v3.clip_id \
            or retarget.clip_id != v3.clip_id:
        raise Spine42V3PipelineChainV2Error(
            "P10.6b v2 project, clip, or address is cross-wired"
        )
    motion_source = motion_v2["source"]
    expected_p9 = {
        "motion_instance_v2_sha256": reviewed.motion_instance_v2_sha256,
        "bundle_sha256": reviewed.bundle_sha256,
    }
    if p9_address != expected_p9 \
            or admission["source"]["p9"] != reviewed.identities \
            or v3_run["inputs"]["p9"] != expected_p9 \
            or p9_run["outputs"]["motion_instance_v2_sha256"] \
                != reviewed.motion_instance_v2_sha256 \
            or expected_p3 != p3 \
            or mesh.p3_rig_sha256 != p3["rig_sha256"] \
            or mesh.p3_bundle_sha256 != p3["bundle_sha256"] \
            or canonical_sha256(mesh.rig) != p3["rig_sha256"] \
            or retarget.instance_sha256 != p5["instance_sha256"] \
            or retarget.bundle_sha256 != p5["bundle_sha256"] \
            or retarget.target_profile_sha256 \
                != p5["target_profile_sha256"] \
            or motion_source["base_motion_instance_sha256"] \
                != p5["instance_sha256"] \
            or motion_source["base_retarget_bundle_sha256"] \
                != p5["bundle_sha256"] \
            or retarget.source_addresses.get("p3_rig_sha256") \
                != p3["rig_sha256"] \
            or retarget.source_addresses.get("p3_bundle_sha256") \
                != p3["bundle_sha256"]:
        raise Spine42V3PipelineChainV2Error(
            "P10.6b v2 P9, P5, P3, or rig source chain differs"
        )
    target_p3 = require_object(target.get("source"), "target source").get(
        "p3"
    )
    instance_source, admission_source = instance["source"], admission["source"]
    if target.get("project_id") != project \
            or not isinstance(target_p3, Mapping) \
            or target_p3.get("rig_sha256") != p3["rig_sha256"] \
            or target_p3.get("bundle_sha256") != p3["bundle_sha256"] \
            or target_sha != p5["target_profile_sha256"] \
            or motion_source["target_profile_sha256"] != target_sha \
            or instance_source["target_profile_sha256"] != target_sha \
            or instance_source["rig_ir_sha256"] != p3["rig_sha256"] \
            or admission_source["target_profile_sha256"] != target_sha \
            or admission_source["p3_rig_sha256"] != p3["rig_sha256"] \
            or admission_source["p3_bundle_sha256"] != p3["bundle_sha256"] \
            or v3.target_profile_sha256 != target_sha \
            or v3.rig_ir_sha256 != p3["rig_sha256"]:
        raise Spine42V3PipelineChainV2Error(
            "P10.6b v2 rig or target-profile binding differs"
        )


def require_digest_source(value, fields, label):
    if type(value) is not dict or set(value) != set(fields) \
            or any(type(value.get(field)) is not str
                   or len(value[field]) != 64
                   or any(char not in "0123456789abcdef" for char in value[field])
                   for field in fields):
        raise Spine42V3PipelineChainV2Error(f"{label} is invalid")
    return {field: value[field] for field in fields}


def require_object(value: Any, label: str):
    if type(value) is not dict:
        raise Spine42V3PipelineChainV2Error(f"{label} must be an object")
    return value


__all__ = [
    "Spine42V3PipelineChainV2Error", "require_digest_source",
    "require_exact_spine42_v3_chain_v2", "require_object",
]
