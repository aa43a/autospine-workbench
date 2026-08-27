"""Deterministic provenance for immutable MotionInstance v3 bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any


FORMAT = "autospine-body-sway-motion-instance-v3-bundle-run"
FORMAT_VERSION = 1
COMPILER = {
    "id": "autospine-body-sway-motion-instance-v3-bundle-compiler",
    "version": "1.0.0",
}
MAX_RUN_BYTES = 1024 * 1024
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_TOP = {
    "format", "format_version", "project_id", "clip_id",
    "inputs", "outputs", "compiler",
}
_INPUTS = {
    "body_sway_motion_consumer_admission_sha256", "p9",
    "motion_domain_sha256", "rotation_timeline_sha256",
    "base_channels_sha256", "rig_ir_sha256", "target_profile_sha256",
}
_P9 = {"motion_instance_v2_sha256", "bundle_sha256"}
_OUTPUTS = {
    "motion_instance_v3_sha256", "motion_instance_v3_profile_sha256",
}


class MotionInstanceV3BundleRunError(ValueError):
    """Raised when bundle provenance is incomplete or ambiguous."""


@dataclass(frozen=True, slots=True)
class MotionInstanceV3BundleRun:
    """Frozen canonical run evidence."""

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


def build_motion_instance_v3_bundle_run(
    project_id: str,
    clip_id: str,
    *,
    body_sway_motion_consumer_admission_sha256: str,
    p9: Mapping[str, Any],
    motion_domain_sha256: str,
    rotation_timeline_sha256: str,
    base_channels_sha256: str,
    rig_ir_sha256: str,
    target_profile_sha256: str,
    motion_instance_v3_sha256: str,
    motion_instance_v3_profile_sha256: str,
) -> MotionInstanceV3BundleRun:
    """Build canonical evidence from already verified exact identities."""

    document = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "project_id": project_id,
        "clip_id": clip_id,
        "inputs": {
            "body_sway_motion_consumer_admission_sha256":
                body_sway_motion_consumer_admission_sha256,
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
        "compiler": dict(COMPILER),
    }
    require_motion_instance_v3_bundle_run(document)
    return MotionInstanceV3BundleRun(_canonical(document).decode("utf-8"))


def require_motion_instance_v3_bundle_run(
    document: Mapping[str, Any],
    *,
    expected: Mapping[str, Any] | None = None,
) -> None:
    """Require the complete run contract and optionally one exact value."""

    try:
        root = _object(document, "MotionInstance v3 bundle run")
        _exact(root, _TOP, "MotionInstance v3 bundle run")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root["format_version"] != FORMAT_VERSION:
            raise MotionInstanceV3BundleRunError(
                "MotionInstance v3 bundle run format is unsupported"
            )
        _token(root.get("project_id"), "project_id")
        _token(root.get("clip_id"), "clip_id")
        inputs = _object(root.get("inputs"), "bundle run inputs")
        _exact(inputs, _INPUTS, "bundle run inputs")
        p9 = _object(inputs.get("p9"), "bundle run P9")
        _exact(p9, _P9, "bundle run P9")
        for field in _P9:
            _digest(p9.get(field), f"p9.{field}")
        for field in _INPUTS - {"p9"}:
            _digest(inputs.get(field), field)
        outputs = _object(root.get("outputs"), "bundle run outputs")
        _exact(outputs, _OUTPUTS, "bundle run outputs")
        for field in _OUTPUTS:
            _digest(outputs.get(field), field)
        if root.get("compiler") != COMPILER:
            raise MotionInstanceV3BundleRunError(
                "MotionInstance v3 bundle compiler identity is unsupported"
            )
        encoded = _canonical(root)
        if len(encoded) > MAX_RUN_BYTES:
            raise MotionInstanceV3BundleRunError(
                "MotionInstance v3 bundle run exceeds its byte limit"
            )
        if expected is not None and encoded != _canonical(expected):
            raise MotionInstanceV3BundleRunError(
                "MotionInstance v3 bundle run differs from exact inputs"
            )
    except MotionInstanceV3BundleRunError:
        raise
    except (OverflowError, TypeError, UnicodeError, ValueError) as exc:
        raise MotionInstanceV3BundleRunError(
            f"MotionInstance v3 bundle run validation failed: {exc}"
        ) from exc


def _token(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise MotionInstanceV3BundleRunError(f"Bundle run {label} is invalid")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise MotionInstanceV3BundleRunError(f"Bundle run {label} is invalid")
    return value


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MotionInstanceV3BundleRunError(f"{label} must be an object")
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise MotionInstanceV3BundleRunError(f"{label} fields are unsupported")


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


__all__ = [
    "COMPILER", "MotionInstanceV3BundleRun",
    "MotionInstanceV3BundleRunError", "build_motion_instance_v3_bundle_run",
    "require_motion_instance_v3_bundle_run",
]
