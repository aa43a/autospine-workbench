"""Deterministic provenance for P10.6b v2 MotionInstance v3 bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any


FORMAT = "autospine-body-sway-motion-instance-v3-bundle-run"
FORMAT_VERSION = 2
COMPILER = {
    "id": "autospine-body-sway-motion-instance-v3-bundle-compiler-v2",
    "version": "2.0.0",
}
AUTHORITY = {
    "motion_instance_v3_emitted": True,
    "attachment_area_overlap_assessed": False,
    "dynamic_seam_safety": False,
    "full_attachment_boundary_continuity": False,
    "publishable_timeline": False,
    "spine_adapter_emitted": False,
    "runtime_equivalence": False,
    "raster_visual_quality": False,
    "persistent_current_head_authority": False,
    "release_authority": False,
}
RELEASE_GATE = {
    "status": "blocked",
    "reason_codes": [
        "attachment_area_overlap_not_assessed",
        "dynamic_seam_safety_unproven",
        "full_attachment_boundary_raster_visual_regression_missing",
        "persistent_current_head_authority_not_granted",
        "publishable_timeline_not_emitted",
        "raster_visual_quality_unproven",
        "runtime_equivalence_unproven",
        "spine_adapter_not_emitted",
    ],
}
MAX_RUN_BYTES = 1024 * 1024
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_TOP = {
    "format", "format_version", "project_id", "clip_id", "inputs",
    "outputs", "authority", "release_gate", "compiler",
}
_INPUTS = {
    "body_sway_motion_consumer_admission_v2_sha256",
    "body_sway_dynamic_seam_v2", "p9", "motion_domain_sha256",
    "rotation_timeline_sha256", "base_channels_sha256",
    "rig_ir_sha256", "target_profile_sha256",
}
_DYNAMIC = {
    "source_set_sha256", "source_document_sha256", "probe_sha256",
    "bundle_sha256",
}
_P9 = {"motion_instance_v2_sha256", "bundle_sha256"}
_OUTPUTS = {
    "motion_instance_v3_sha256", "motion_instance_v3_profile_sha256",
}


class MotionInstanceV3BundleRunV2Error(ValueError):
    """Raised when v2 bundle provenance is incomplete or ambiguous."""


@dataclass(frozen=True, slots=True)
class MotionInstanceV3BundleRunV2:
    _canonical_json: str = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


def build_motion_instance_v3_bundle_run_v2(
    project_id: str,
    clip_id: str,
    *,
    admission_sha256: str,
    dynamic_seam: Mapping[str, Any],
    p9: Mapping[str, Any],
    motion_domain_sha256: str,
    rotation_timeline_sha256: str,
    base_channels_sha256: str,
    rig_ir_sha256: str,
    target_profile_sha256: str,
    motion_instance_v3_sha256: str,
    motion_instance_v3_profile_sha256: str,
) -> MotionInstanceV3BundleRunV2:
    document = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "project_id": project_id,
        "clip_id": clip_id,
        "inputs": {
            "body_sway_motion_consumer_admission_v2_sha256":
                admission_sha256,
            "body_sway_dynamic_seam_v2": dict(dynamic_seam),
            "p9": dict(p9),
            "motion_domain_sha256": motion_domain_sha256,
            "rotation_timeline_sha256": rotation_timeline_sha256,
            "base_channels_sha256": base_channels_sha256,
            "rig_ir_sha256": rig_ir_sha256,
            "target_profile_sha256": target_profile_sha256,
        },
        "outputs": {
            "motion_instance_v3_sha256": motion_instance_v3_sha256,
            "motion_instance_v3_profile_sha256":
                motion_instance_v3_profile_sha256,
        },
        "authority": dict(AUTHORITY),
        "release_gate": {
            "status": RELEASE_GATE["status"],
            "reason_codes": list(RELEASE_GATE["reason_codes"]),
        },
        "compiler": dict(COMPILER),
    }
    require_motion_instance_v3_bundle_run_v2(document)
    return MotionInstanceV3BundleRunV2(_canonical(document).decode("utf-8"))


def require_motion_instance_v3_bundle_run_v2(
    document: Mapping[str, Any], *, expected: Mapping[str, Any] | None = None,
) -> None:
    """Require the complete v2 run contract and optional exact value."""

    try:
        root = _object(document, "MotionInstance v3 v2 bundle run")
        _exact(root, _TOP, "bundle run")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root["format_version"] != FORMAT_VERSION:
            raise MotionInstanceV3BundleRunV2Error(
                "MotionInstance v3 v2 bundle run format is unsupported"
            )
        _token(root.get("project_id"), "project_id")
        _token(root.get("clip_id"), "clip_id")
        inputs = _object(root.get("inputs"), "bundle run inputs")
        _exact(inputs, _INPUTS, "bundle run inputs")
        _digest(
            inputs.get("body_sway_motion_consumer_admission_v2_sha256"),
            "admission_v2_sha256",
        )
        _digest_object(inputs.get("body_sway_dynamic_seam_v2"), _DYNAMIC,
                       "dynamic seam v2")
        _digest_object(inputs.get("p9"), _P9, "P9")
        for name in _INPUTS - {
            "body_sway_motion_consumer_admission_v2_sha256",
            "body_sway_dynamic_seam_v2", "p9",
        }:
            _digest(inputs.get(name), name)
        outputs = _object(root.get("outputs"), "bundle run outputs")
        _exact(outputs, _OUTPUTS, "bundle run outputs")
        for name in _OUTPUTS:
            _digest(outputs.get(name), name)
        if root.get("authority") != AUTHORITY \
                or root.get("release_gate") != RELEASE_GATE \
                or root.get("compiler") != COMPILER:
            raise MotionInstanceV3BundleRunV2Error(
                "MotionInstance v3 v2 bundle policy is unsupported"
            )
        encoded = _canonical(root)
        if len(encoded) > MAX_RUN_BYTES:
            raise MotionInstanceV3BundleRunV2Error(
                "MotionInstance v3 v2 bundle run exceeds its byte limit"
            )
        if expected is not None and encoded != _canonical(expected):
            raise MotionInstanceV3BundleRunV2Error(
                "MotionInstance v3 v2 bundle run differs from exact inputs"
            )
    except MotionInstanceV3BundleRunV2Error:
        raise
    except (OverflowError, TypeError, UnicodeError, ValueError) as exc:
        raise MotionInstanceV3BundleRunV2Error(
            f"MotionInstance v3 v2 run validation failed: {exc}"
        ) from exc


def _digest_object(value, fields, label):
    row = _object(value, f"bundle run {label}")
    _exact(row, fields, f"bundle run {label}")
    for name in fields:
        _digest(row.get(name), f"{label}.{name}")


def _token(value, label):
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise MotionInstanceV3BundleRunV2Error(f"Bundle run {label} is invalid")


def _digest(value, label):
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise MotionInstanceV3BundleRunV2Error(f"Bundle run {label} is invalid")


def _object(value, label):
    if not isinstance(value, Mapping):
        raise MotionInstanceV3BundleRunV2Error(f"{label} must be an object")
    return value


def _exact(value, fields, label):
    if set(value) != fields:
        raise MotionInstanceV3BundleRunV2Error(f"{label} fields are unsupported")


def _canonical(value):
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


__all__ = [
    "AUTHORITY", "COMPILER", "MAX_RUN_BYTES", "RELEASE_GATE",
    "MotionInstanceV3BundleRunV2", "MotionInstanceV3BundleRunV2Error",
    "build_motion_instance_v3_bundle_run_v2",
    "require_motion_instance_v3_bundle_run_v2",
]
