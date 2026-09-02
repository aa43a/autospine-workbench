"""Version-isolated P10.6b v2 source contract for the Spine adapter."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from types import MappingProxyType
from typing import Any

from .body_sway_motion_consumer_profile_v2 import (
    FORMAT as ADMISSION_FORMAT, FORMAT_VERSION as ADMISSION_VERSION,
)
from .motion_instance_v3_bundle_reader_v2 import (
    VerifiedMotionInstanceV3BundleV2,
)
from .motion_instance_v3_shape import (
    MotionInstanceV3ShapeError, require_motion_instance_v3_shape,
)
from .motion_target_validation import (
    MotionTargetValidationError, require_motion_target_profile,
)
from .resolved_project import canonical_sha256
from .reviewed_motion_bundle_integrity import VerifiedReviewedMotionBundle
from .spine42_contract_v3 import spine42_target_profile_v3
from .spine42_rig_validation import (
    Spine42RigValidationError, require_spine42_rig,
)

_SOURCE_CONTRACT = {
    "id": "autospine-spine42-motion-instance-v3-source",
    "version": 2,
    "motion_bundle_run_format":
        "autospine-body-sway-motion-instance-v3-bundle-run",
    "motion_bundle_run_format_version": 2,
    "admission_document":
        "body-sway-motion-consumer-admission-v2.json",
    "motion_document": "motion-instance-v3.json",
    "run_document": "run-manifest-v2.json",
}
SOURCE_CONTRACT = MappingProxyType(_SOURCE_CONTRACT)
PROFILE_HASH_DOMAIN = "autospine-spine42-json-adapter-v3-profile/v2"
SOURCE_HASH_DOMAIN = "autospine-spine42-motion-instance-v3-source/v2"
_PROFILE = spine42_target_profile_v3()
_PROFILE["source_contract"] = dict(_SOURCE_CONTRACT)
MOTION_SOURCE_FIELDS = (
    "motion_instance_v3_sha256", "bundle_sha256", "admission_sha256",
    "source_set_sha256", "source_document_sha256",
    "dynamic_seam_probe_sha256", "dynamic_seam_bundle_sha256",
    "motion_instance_v2_sha256", "reviewed_motion_bundle_sha256",
    "motion_instance_v3_profile_sha256", "motion_domain_sha256",
    "rotation_timeline_sha256", "base_channels_sha256", "rig_ir_sha256",
    "target_profile_sha256", "run_sha256",
)


class Spine42ContractV3V2Error(ValueError):
    """Raised when a P10.6b v2 source exceeds the pinned adapter."""


@dataclass(frozen=True, slots=True)
class Spine42V3InputBindingsV2:
    adapter_profile_sha256: str
    source_contract_sha256: str
    motion_instance_v3_source_sha256: str
    rig_sha256: str
    motion_instance_v3_sha256: str
    motion_instance_v3_bundle_sha256: str
    motion_instance_v3_profile_sha256: str
    target_profile_sha256: str


def spine42_source_contract_v3_v2() -> dict[str, Any]:
    return _copy(_SOURCE_CONTRACT, "Spine v2 source contract")


def spine42_source_contract_v3_v2_sha256() -> str:
    return canonical_sha256({
        "domain": "autospine-spine42-source-contract/v2",
        "contract": _SOURCE_CONTRACT,
    })


def spine42_target_profile_v3_v2() -> dict[str, Any]:
    return _copy(_PROFILE, "Spine 4.2 adapter v3 v2-source profile")


def spine42_target_profile_v3_v2_sha256() -> str:
    return canonical_sha256({
        "domain": PROFILE_HASH_DOMAIN, "profile": _PROFILE,
    })


def spine42_motion_source_v3_v2(
    bundle: VerifiedMotionInstanceV3BundleV2,
) -> dict[str, str]:
    if type(bundle) is not VerifiedMotionInstanceV3BundleV2:
        raise Spine42ContractV3V2Error(
            "P10.7a v2 requires a reader-issued P10.6b v2 bundle"
        )
    return {
        name: getattr(bundle, name) for name in MOTION_SOURCE_FIELDS
    }


def spine42_motion_source_v3_v2_sha256(source: Mapping[str, str]) -> str:
    value = _digest_source(source)
    return canonical_sha256({
        "domain": SOURCE_HASH_DOMAIN, "source": value,
    })


def require_spine42_inputs_v3_v2(
    rig: Mapping[str, Any], *,
    motion_bundle: VerifiedMotionInstanceV3BundleV2,
    reviewed_bundle: VerifiedReviewedMotionBundle,
    target_profile: Mapping[str, Any],
    adapter_profile: Mapping[str, Any] | None = None,
) -> Spine42V3InputBindingsV2:
    """Admit only one exact reader-issued P10.6b v2/P9/P3 chain."""

    try:
        if type(motion_bundle) is not VerifiedMotionInstanceV3BundleV2 \
                or type(reviewed_bundle) is not VerifiedReviewedMotionBundle:
            raise Spine42ContractV3V2Error(
                "P10.7a v2 requires reader-issued exact upstream bundles"
            )
        selected = spine42_target_profile_v3_v2() \
            if adapter_profile is None else _copy(
                adapter_profile, "Spine 4.2 v2-source adapter profile",
            )
        if selected != _PROFILE:
            raise Spine42ContractV3V2Error(
                "Spine 4.2 v2-source adapter profile is unsupported"
            )
        require_spine42_rig(rig)
        require_motion_target_profile(target_profile)
        instance = motion_bundle.document("motion-instance-v3.json")
        admission = motion_bundle.document(
            "body-sway-motion-consumer-admission-v2.json"
        )
        run = motion_bundle.document("run-manifest-v2.json")
        require_motion_instance_v3_shape(instance)
        source = spine42_motion_source_v3_v2(motion_bundle)
        _require_bundle_documents(motion_bundle, instance, admission, run)
        rig_sha, target_sha = canonical_sha256(rig), \
            canonical_sha256(target_profile)
        _require_cross_bindings(
            rig, target_profile, reviewed_bundle, motion_bundle,
            instance, admission, run, rig_sha, target_sha,
        )
        return Spine42V3InputBindingsV2(
            spine42_target_profile_v3_v2_sha256(),
            spine42_source_contract_v3_v2_sha256(),
            spine42_motion_source_v3_v2_sha256(source),
            rig_sha, motion_bundle.motion_instance_v3_sha256,
            motion_bundle.bundle_sha256,
            motion_bundle.motion_instance_v3_profile_sha256, target_sha,
        )
    except Spine42ContractV3V2Error:
        raise
    except (
        AttributeError, KeyError, MotionInstanceV3ShapeError,
        MotionTargetValidationError, OverflowError, Spine42RigValidationError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise Spine42ContractV3V2Error(
            f"Spine 4.2 v2-source input validation failed: {exc}"
        ) from exc


def _require_bundle_documents(bundle, instance, admission, run):
    source = instance["source"]
    if canonical_sha256(instance) != bundle.motion_instance_v3_sha256 \
            or canonical_sha256(admission) != bundle.admission_sha256 \
            or admission.get("format") != ADMISSION_FORMAT \
            or admission.get("format_version") != ADMISSION_VERSION \
            or run.get("format_version") != 2 \
            or run.get("outputs", {}).get("motion_instance_v3_sha256") \
                != bundle.motion_instance_v3_sha256 \
            or source["body_sway_motion_consumer_admission_sha256"] \
                != bundle.admission_sha256:
        raise Spine42ContractV3V2Error(
            "P10.6b v2 documents differ from their exact identities"
        )


def _require_cross_bindings(
    rig, target, reviewed, bundle, instance, admission, run,
    rig_sha, target_sha,
):
    instance_source, admission_source = instance["source"], admission["source"]
    p9 = {"motion_instance_v2_sha256": reviewed.motion_instance_v2_sha256,
          "bundle_sha256": reviewed.bundle_sha256}
    p9_motion = reviewed.document("motion-instance-v2.json")
    p9_source = p9_motion["source"]
    target_p3 = target["source"]["p3"]
    admission_p9 = admission_source["p9"]
    if bundle.project_id != reviewed.project_id \
            or bundle.clip_id != reviewed.clip_id \
            or admission.get("project_id") != bundle.project_id \
            or admission.get("clip_id") != bundle.clip_id \
            or instance.get("clip_id") != bundle.clip_id \
            or instance_source["p9"] != p9 \
            or admission_p9 != reviewed.identities \
            or run["inputs"]["p9"] != p9:
        raise Spine42ContractV3V2Error(
            "P10.6b v2 project, clip, or P9 source is cross-wired"
        )
    if rig_sha != bundle.rig_ir_sha256 \
            or admission_source["p3_rig_sha256"] != rig_sha \
            or p9_source["p3_rig_sha256"] != rig_sha \
            or target_p3["rig_sha256"] != rig_sha \
            or target_p3["bundle_sha256"] != p9_source["p3_bundle_sha256"] \
            or admission_source["p3_bundle_sha256"] \
                != p9_source["p3_bundle_sha256"]:
        raise Spine42ContractV3V2Error("P10.6b v2 P3 source is cross-wired")
    if target_sha != bundle.target_profile_sha256 \
            or admission_source["target_profile_sha256"] != target_sha \
            or p9_source["target_profile_sha256"] != target_sha \
            or target.get("project_id") != bundle.project_id \
            or target.get("target_space", {}).get("canvas") != rig.get("canvas"):
        raise Spine42ContractV3V2Error(
            "P10.6b v2 target profile is cross-wired"
        )


def _digest_source(value):
    if type(value) is not dict or set(value) != set(MOTION_SOURCE_FIELDS) \
            or any(type(value[name]) is not str or len(value[name]) != 64
                   or any(char not in "0123456789abcdef" for char in value[name])
                   for name in MOTION_SOURCE_FIELDS):
        raise Spine42ContractV3V2Error(
            "P10.6b v2 motion source identity is invalid"
        )
    return {name: value[name] for name in MOTION_SOURCE_FIELDS}


def _copy(value, label):
    if not isinstance(value, Mapping):
        raise Spine42ContractV3V2Error(f"{label} must be an object")
    try:
        result = json.loads(json.dumps(
            dict(value), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ))
    except (OverflowError, TypeError, ValueError) as exc:
        raise Spine42ContractV3V2Error(f"{label} is not strict JSON") from exc
    if type(result) is not dict:
        raise Spine42ContractV3V2Error(f"{label} must be an object")
    return result


__all__ = [
    "MOTION_SOURCE_FIELDS", "SOURCE_CONTRACT", "Spine42ContractV3V2Error",
    "Spine42V3InputBindingsV2", "require_spine42_inputs_v3_v2",
    "spine42_motion_source_v3_v2", "spine42_motion_source_v3_v2_sha256",
    "spine42_source_contract_v3_v2",
    "spine42_source_contract_v3_v2_sha256",
    "spine42_target_profile_v3_v2",
    "spine42_target_profile_v3_v2_sha256",
]
