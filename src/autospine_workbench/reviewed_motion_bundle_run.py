"""Strict provenance for immutable reviewed-motion bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any


FORMAT = "autospine-reviewed-motion-bundle-run"
FORMAT_VERSION = 1
COMPILER = {
    "id": "autospine-reviewed-motion-bundle-compiler",
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
    "p3", "p5", "foot_lock_candidates_sha256",
    "depth_order_candidates_sha256", "motion_policy_decision_sha256",
}
_P3 = {"rig_sha256", "bundle_sha256"}
_P5 = {"instance_sha256", "bundle_sha256", "target_profile_sha256"}
_OUTPUTS = {"reviewed_motion_policy_sha256", "motion_instance_v2_sha256"}


class ReviewedMotionBundleRunError(ValueError):
    """Raised when reviewed-motion provenance is incomplete or ambiguous."""


@dataclass(frozen=True, slots=True)
class ReviewedMotionBundleRun:
    """Frozen canonical run evidence."""

    _canonical_json: str

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


def build_reviewed_motion_bundle_run(
    project_id: str,
    clip_id: str,
    *,
    p3: Mapping[str, Any],
    p5: Mapping[str, Any],
    foot_lock_candidates_sha256: str,
    depth_order_candidates_sha256: str,
    motion_policy_decision_sha256: str,
    reviewed_motion_policy_sha256: str,
    motion_instance_v2_sha256: str,
) -> ReviewedMotionBundleRun:
    """Build canonical evidence from already verified exact identities."""

    document = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "project_id": project_id,
        "clip_id": clip_id,
        "inputs": {
            "p3": dict(p3),
            "p5": dict(p5),
            "foot_lock_candidates_sha256": foot_lock_candidates_sha256,
            "depth_order_candidates_sha256": depth_order_candidates_sha256,
            "motion_policy_decision_sha256": motion_policy_decision_sha256,
        },
        "outputs": {
            "reviewed_motion_policy_sha256": reviewed_motion_policy_sha256,
            "motion_instance_v2_sha256": motion_instance_v2_sha256,
        },
        "compiler": dict(COMPILER),
    }
    require_reviewed_motion_bundle_run(document)
    return ReviewedMotionBundleRun(_canonical(document).decode("utf-8"))


def require_reviewed_motion_bundle_run(
    document: Mapping[str, Any],
    *,
    expected: Mapping[str, Any] | None = None,
) -> None:
    """Require the complete v1 contract and optionally exact expected value."""

    try:
        root = _object(document, "Reviewed-motion bundle run")
        _exact(root, _TOP, "Reviewed-motion bundle run")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root.get("format_version") != FORMAT_VERSION:
            raise ReviewedMotionBundleRunError(
                "Reviewed-motion bundle run format is unsupported"
            )
        _token(root.get("project_id"), "project_id")
        _token(root.get("clip_id"), "clip_id")
        inputs = _object(root.get("inputs"), "Reviewed-motion inputs")
        _exact(inputs, _INPUTS, "Reviewed-motion inputs")
        _digest_object(inputs.get("p3"), _P3, "P3 inputs")
        _digest_object(inputs.get("p5"), _P5, "P5 inputs")
        for field in _INPUTS - {"p3", "p5"}:
            _digest(inputs.get(field), field)
        outputs = _digest_object(
            root.get("outputs"), _OUTPUTS, "Reviewed-motion outputs"
        )
        if root.get("compiler") != COMPILER:
            raise ReviewedMotionBundleRunError(
                "Reviewed-motion bundle compiler identity is unsupported"
            )
        encoded = _canonical(root)
        if len(encoded) > MAX_RUN_BYTES:
            raise ReviewedMotionBundleRunError(
                "Reviewed-motion bundle run exceeds its byte limit"
            )
        if expected is not None and _canonical(root) != _canonical(expected):
            raise ReviewedMotionBundleRunError(
                "Reviewed-motion bundle run differs from exact inputs"
            )
        if not outputs:
            raise ReviewedMotionBundleRunError("Reviewed-motion outputs are empty")
    except ReviewedMotionBundleRunError:
        raise
    except (OverflowError, TypeError, UnicodeError, ValueError) as exc:
        raise ReviewedMotionBundleRunError(
            f"Reviewed-motion bundle run validation failed: {exc}"
        ) from exc


def _digest_object(value: Any, fields: set[str], label: str) -> Mapping[str, Any]:
    row = _object(value, label)
    _exact(row, fields, label)
    for field in fields:
        _digest(row.get(field), f"{label}.{field}")
    return row


def _token(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise ReviewedMotionBundleRunError(f"Reviewed-motion {label} is invalid")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ReviewedMotionBundleRunError(f"Reviewed-motion {label} is invalid")
    return value


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReviewedMotionBundleRunError(f"{label} must be an object")
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise ReviewedMotionBundleRunError(f"{label} fields are unsupported")


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
