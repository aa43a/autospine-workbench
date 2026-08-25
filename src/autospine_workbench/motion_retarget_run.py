"""Acyclic, domain-separated provenance contract for MotionIR retargeting."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import math
import re
from typing import Any

from .motion_instance_validation import (
    MotionInstanceValidationError,
    instance_sha256,
    require_motion_instance,
)


FORMAT, FORMAT_VERSION = "autospine-retarget-run", 1
COMPILER_ID, COMPILER_VERSION = "setup-local-motion-retargeter", "1.0.0"
RUN_IDENTITY_DOMAIN = b"autospine-retarget-run-identity/v1"
MAX_RUN_BYTES = 64 * 1024
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_VERSION = re.compile(r"^[0-9]+(?:\.[0-9]+){2}$")
_TOP = {
    "format", "format_version", "run_identity_sha256",
    "inputs", "compiler", "output",
}
_INPUT_FIELDS = {
    "motion_ir_sha256", "motion_bundle_sha256", "motion_run_sha256",
    "target_profile_sha256",
}
_CONFIG = {
    "profile": "humanoid-setup-local-v1",
    "ik_solver_id": "autospine-two-bone-analytic",
    "ik_solver_version": "1.0.0",
    "ik_unreachable_policy": "reject",
    "rotation_conflict_policy": "reject",
    "numeric_precision_decimals": 12,
}


class RetargetRunValidationError(ValueError):
    """Raised when retarget provenance is malformed, stale, or cross-wired."""


def retarget_compiler() -> dict[str, Any]:
    """Return the only compiler identity/configuration accepted by v1."""
    return {
        "id": COMPILER_ID,
        "version": COMPILER_VERSION,
        "config": dict(_CONFIG),
    }


def retarget_run_identity_sha256(
    inputs: Mapping[str, Any],
    compiler: Mapping[str, Any] | None = None,
) -> str:
    """Hash run intent only; output is deliberately absent to avoid a SHA cycle.

    This helper accepts any structurally valid compiler projection so identity
    sensitivity can be audited. ``require_retarget_run`` separately pins the
    compiler to the supported v1 implementation.
    """
    clean_inputs = _inputs(inputs)
    clean_compiler = _compiler(
        retarget_compiler() if compiler is None else compiler,
        require_supported=False,
    )
    projection = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "inputs": clean_inputs,
        "compiler": clean_compiler,
    }
    digest = hashlib.sha256()
    _feed(digest, RUN_IDENTITY_DOMAIN)
    _feed(digest, _canonical(projection))
    return digest.hexdigest()


def require_retarget_run(
    document: Mapping[str, Any],
    *,
    instance: Mapping[str, Any] | None = None,
) -> None:
    """Validate the manifest and optionally cross-bind its full output instance."""
    try:
        root = _object(document, "Retarget run")
        _strict_json_tree(root)
        _exact(root, _TOP, "Retarget run")
        if root.get("format") != FORMAT or type(root.get("format_version")) is not int \
                or root.get("format_version") != FORMAT_VERSION:
            raise RetargetRunValidationError("Retarget run format is unsupported")
        inputs = _inputs(root.get("inputs"))
        compiler = _compiler(root.get("compiler"), require_supported=True)
        identity = root.get("run_identity_sha256")
        _sha(identity, "Retarget run identity")
        if identity != retarget_run_identity_sha256(inputs, compiler):
            raise RetargetRunValidationError("Retarget run identity is stale")
        output = _object(root.get("output"), "Retarget run output")
        _exact(output, {"instance_sha256"}, "Retarget run output")
        _sha(output.get("instance_sha256"), "Retarget run output instance")
        if instance is not None:
            _cross_instance(root, instance)
        if len(_canonical(root)) > MAX_RUN_BYTES:
            raise RetargetRunValidationError("Retarget run byte limit exceeded")
    except RetargetRunValidationError:
        raise
    except (MotionInstanceValidationError, KeyError, OverflowError,
            TypeError, ValueError) as exc:
        raise RetargetRunValidationError(
            f"Retarget run validation failed: {exc}"
        ) from exc


def retarget_run_document_sha256(document: Mapping[str, Any]) -> str:
    """Hash the complete run, including output; this is not its run identity."""
    require_retarget_run(document)
    return hashlib.sha256(_canonical(document)).hexdigest()


def _cross_instance(run: Mapping[str, Any], instance: Mapping[str, Any]) -> None:
    require_motion_instance(instance)
    inputs, source = run["inputs"], instance["source"]
    if any(source.get(field) != inputs.get(field) for field in _INPUT_FIELDS):
        raise RetargetRunValidationError("Instance input identity chain differs")
    if source.get("retarget_run_identity_sha256") != run["run_identity_sha256"]:
        raise RetargetRunValidationError("Instance retarget run identity differs")
    if instance_sha256(instance) != run["output"]["instance_sha256"]:
        raise RetargetRunValidationError("Retarget run output instance differs")


def _inputs(value: Any) -> dict[str, str]:
    inputs = _object(value, "Retarget run inputs")
    _exact(inputs, _INPUT_FIELDS, "Retarget run inputs")
    result = {}
    for field in sorted(_INPUT_FIELDS):
        _sha(inputs.get(field), field)
        result[field] = inputs[field]
    return result


def _compiler(value: Any, *, require_supported: bool) -> dict[str, Any]:
    compiler = _object(value, "Retarget compiler")
    _exact(compiler, {"id", "version", "config"}, "Retarget compiler")
    compiler_id, version = compiler.get("id"), compiler.get("version")
    if not isinstance(compiler_id, str) or not _SAFE_TOKEN.fullmatch(compiler_id) \
            or not isinstance(version, str) or len(version) > 32 \
            or not _VERSION.fullmatch(version):
        raise RetargetRunValidationError("Retarget compiler identity is invalid")
    config = _object(compiler.get("config"), "Retarget compiler config")
    _exact(config, set(_CONFIG), "Retarget compiler config")
    for field in set(_CONFIG) - {"numeric_precision_decimals"}:
        if not isinstance(config.get(field), str) \
                or not _SAFE_TOKEN.fullmatch(config[field]):
            raise RetargetRunValidationError("Retarget compiler config is invalid")
    precision = config.get("numeric_precision_decimals")
    if type(precision) is not int or not 0 <= precision <= 18:
        raise RetargetRunValidationError("Retarget numeric precision is invalid")
    result = {"id": compiler_id, "version": version, "config": dict(config)}
    if require_supported and result != retarget_compiler():
        raise RetargetRunValidationError("Retarget compiler is unsupported")
    return result


def _sha(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise RetargetRunValidationError(f"{label} is not a SHA-256 digest")


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RetargetRunValidationError(f"{label} must be an object")
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise RetargetRunValidationError(f"{label} fields are unsupported")


def _strict_json_tree(value: Any) -> None:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise RetargetRunValidationError("JSON keys must be strings")
        for item in value.values():
            _strict_json_tree(item)
    elif isinstance(value, list):
        for item in value:
            _strict_json_tree(item)
    elif isinstance(value, tuple):
        raise RetargetRunValidationError("JSON arrays must be lists")
    elif isinstance(value, float) and not math.isfinite(value):
        raise RetargetRunValidationError("JSON numbers must be finite")


def _feed(digest, value: bytes) -> None:
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
