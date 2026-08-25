"""Pure compilation from one verified MotionIR bundle to MotionInstance v1."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from typing import Any

from .ik_probe_math import quantize
from .motion_bundle_integrity import (
    MotionBundleIntegrityError,
    MotionBundleSnapshot,
    VerifiedMotionBundle,
    verify_motion_bundle_snapshot,
)
from .motion_instance_validation import (
    MotionInstanceValidationError,
    instance_sha256,
    require_motion_instance,
)
from .motion_retarget_kinematics import (
    MotionRetargetKinematicsError,
    solve_motion_ik_track,
)
from . import motion_retarget_run as run_contract
from .motion_roles import CANONICAL_BONE_ID_BY_ROLE
from .motion_target_profile import MotionTargetProfile
from .motion_target_validation import (
    MotionTargetValidationError,
    require_motion_target_profile,
)
from .motion_validation import MotionValidationError, require_motion_ir
from .resolved_project import canonical_sha256


class MotionRetargetCompilerError(ValueError):
    """Raised when verified inputs cannot produce one safe exact instance."""


@dataclass(frozen=True, slots=True)
class RetargetedMotion:
    """Frozen isolated instance and run snapshots with their exact identities."""

    _instance_json: str
    _run_json: str

    @property
    def instance(self) -> dict[str, Any]:
        return json.loads(self._instance_json)

    @property
    def run(self) -> dict[str, Any]:
        return json.loads(self._run_json)

    @property
    def instance_sha256(self) -> str:
        return instance_sha256(self.instance)

    @property
    def run_identity_sha256(self) -> str:
        return str(self.run["run_identity_sha256"])

    @property
    def run_document_sha256(self) -> str:
        return run_contract.retarget_run_document_sha256(self.run)

    @property
    def target_profile_sha(self) -> str:
        return str(self.instance["source"]["target_profile_sha256"])

    @property
    def target_profile_sha256(self) -> str:
        return self.target_profile_sha


def compile_motion_instance(
    verified_motion: VerifiedMotionBundle,
    target_profile: MotionTargetProfile,
) -> RetargetedMotion:
    """Retarget explicit immutable inputs without filesystem access or mutation."""

    try:
        verified = _rebuild_verified_motion(verified_motion)
        target, target_sha = _rebuild_target_profile(target_profile)
        motion = verified.motion
        require_motion_ir(motion)
        inputs = {
            "motion_ir_sha256": verified.clip_sha256,
            "motion_bundle_sha256": verified.bundle_sha256,
            "motion_run_sha256": verified.run_sha256,
            "target_profile_sha256": target_sha,
        }
        compiler = run_contract.retarget_compiler()
        run_identity = run_contract.retarget_run_identity_sha256(inputs, compiler)
        instance = _compile_document(motion, target, inputs, run_identity)
        require_motion_instance(instance, target_profile=target)
        run = {
            "format": run_contract.FORMAT,
            "format_version": run_contract.FORMAT_VERSION,
            "run_identity_sha256": run_identity,
            "inputs": inputs,
            "compiler": compiler,
            "output": {"instance_sha256": instance_sha256(instance)},
        }
        run_contract.require_retarget_run(run, instance=instance)
        return RetargetedMotion(_canonical(instance), _canonical(run))
    except MotionRetargetCompilerError:
        raise
    except (
        MotionBundleIntegrityError,
        MotionInstanceValidationError,
        MotionRetargetKinematicsError,
        MotionTargetValidationError,
        MotionValidationError,
        run_contract.RetargetRunValidationError,
        AttributeError,
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
    ) as exc:
        raise MotionRetargetCompilerError(
            f"Motion instance compilation failed: {exc}"
        ) from exc


def _rebuild_verified_motion(value: Any) -> VerifiedMotionBundle:
    if type(value) is not VerifiedMotionBundle:
        raise MotionRetargetCompilerError(
            "Motion retargeting requires an exact VerifiedMotionBundle"
        )
    try:
        raw = value.document_bytes
        items = tuple((name, raw[name]) for name in value.inventory)
        rebuilt = verify_motion_bundle_snapshot(
            MotionBundleSnapshot(value.path, items),
            expected_clip_sha256=value.clip_sha256,
            expected_bundle_sha256=value.bundle_sha256,
        )
    except (KeyError, MotionBundleIntegrityError, TypeError, ValueError) as exc:
        raise MotionRetargetCompilerError(
            "Verified motion input cannot be exactly rebuilt"
        ) from exc
    if rebuilt != value:
        raise MotionRetargetCompilerError(
            "Verified motion identities differ from rebuilt content"
        )
    return rebuilt


def _rebuild_target_profile(value: Any) -> tuple[dict[str, Any], str]:
    if type(value) is not MotionTargetProfile:
        raise MotionRetargetCompilerError(
            "Motion retargeting requires an exact MotionTargetProfile"
        )
    document = value.document
    require_motion_target_profile(document)
    canonical = _canonical(document)
    if canonical != value._document_json:
        raise MotionRetargetCompilerError(
            "Motion target profile is not its canonical frozen snapshot"
        )
    digest = canonical_sha256(document)
    if digest != value.sha256:
        raise MotionRetargetCompilerError(
            "Motion target profile identity differs from rebuilt content"
        )
    return document, digest


def _compile_document(motion, target, inputs, run_identity):
    tracks: dict[tuple[str, str], dict[str, Any]] = {}
    reference = target["reference_length"]["value_px"]
    for source in motion["tracks"]:
        if source["target_kind"] == "bone_role":
            bone_id = CANONICAL_BONE_ID_BY_ROLE[source["target"]]
            prop = source["property"]
            keys = _direct_keys(source["keys"], prop, reference)
            _add_track(tracks, bone_id, prop, keys)
            continue
        solved = solve_motion_ik_track(motion, target, source["target"])
        if any(sample.reach_state != "reachable" for sample in solved.samples):
            raise MotionRetargetCompilerError(
                f"IK handle {solved.handle_id} contains an unreachable sample"
            )
        _add_track(
            tracks, solved.proximal_bone_id, "rotation",
            _ik_keys(solved.samples, "proximal_rotation_delta_deg"),
        )
        _add_track(
            tracks, solved.distal_bone_id, "rotation",
            _ik_keys(solved.samples, "distal_rotation_delta_deg"),
        )
    return {
        "format": "autospine-motion-instance",
        "format_version": 1,
        "clip_id": motion["clip_id"],
        "timing": {
            "ticks_per_second": motion["ticks_per_second"],
            "duration_ticks": motion["duration_ticks"],
            "loop": motion["loop"],
        },
        "source": {**inputs, "retarget_run_identity_sha256": run_identity},
        "target_space": {
            "translation": "setup-local-pixel",
            "rotation": "setup-local-degree",
            "positive_rotation": "clockwise",
            "interpolation": "linear",
        },
        "tracks": [tracks[key] for key in sorted(tracks)],
        "markers": _markers(motion["markers"], target),
    }


def _direct_keys(keys, prop, reference):
    result = []
    for key in keys:
        value = key["value"]
        if prop == "translation":
            value = [quantize(value[0] * reference), quantize(value[1] * reference)]
        else:
            value = quantize(value)
        result.append({"tick": key["tick"], "value": value})
    return result


def _ik_keys(samples, field):
    return [
        {"tick": sample.tick, "value": quantize(getattr(sample, field))}
        for sample in samples
    ]


def _add_track(tracks, bone_id, prop, keys):
    identity = bone_id, prop
    if identity in tracks:
        raise MotionRetargetCompilerError(
            f"Bone track {bone_id}/{prop} has competing motion drivers"
        )
    tracks[identity] = {"bone_id": bone_id, "property": prop, "keys": keys}


def _markers(markers, target):
    handles = {item["id"]: item for item in target["ik_handles"]}
    return [
        {
            **marker,
            "proximal_bone_id": handles[marker["limb"]]["proximal_bone_id"],
            "distal_bone_id": handles[marker["limb"]]["distal_bone_id"],
        }
        for marker in markers
    ]


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
