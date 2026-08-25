"""Strict input and scalar checks shared by the region-only compiler."""

from __future__ import annotations

import math
from pathlib import PurePosixPath
import re
from typing import Any, Mapping, Sequence

from .resolved_project import canonical_sha256


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class RegionRigContractError(ValueError):
    """Raised when a compile input does not satisfy its pinned contract."""


def validate_compile_inputs(
    manifest: Mapping[str, Any], resolved: Mapping[str, Any], layer_sha: str
) -> dict[str, Any]:
    manifest = mapping(manifest, "Layer Manifest")
    resolved = mapping(resolved, "resolved project")
    if manifest.get("format") != "autospine-layer-manifest" or manifest.get("format_version") != 1:
        raise RegionRigContractError("Unsupported Layer Manifest")
    if resolved.get("schema_version") != "autospine.resolved-project/v1":
        raise RegionRigContractError("Unsupported resolved project")
    layer_sha = required_sha(layer_sha, "layer manifest")
    if _canonical(manifest, "Layer Manifest") != layer_sha:
        raise RegionRigContractError("Layer Manifest content does not match its SHA-256")
    resolved_sha = required_sha(resolved.get("sha256"), "resolved project")
    unhashed = dict(resolved)
    unhashed.pop("sha256", None)
    if _canonical(unhashed, "resolved project") != resolved_sha:
        raise RegionRigContractError("Resolved project self-hash is invalid")
    project_id = manifest.get("project_id")
    if not isinstance(project_id, str) or not _SAFE_ID.fullmatch(project_id):
        raise RegionRigContractError("Project id is invalid")
    if resolved.get("project_id") != project_id:
        raise RegionRigContractError("Layer Manifest and resolved project ids differ")
    revision = manifest.get("revision")
    if not is_integer(revision) or resolved.get("revision") != revision:
        raise RegionRigContractError("Layer Manifest and resolved revisions differ")
    source = mapping(manifest.get("source"), "Layer Manifest source")
    canvas = positive_size(source.get("canvas"), "Layer Manifest canvas")
    resolved_canvas = mapping(resolved.get("canvas"), "resolved canvas")
    if [resolved_canvas.get("width"), resolved_canvas.get("height")] != canvas:
        raise RegionRigContractError("Layer Manifest and resolved canvases differ")
    inputs = mapping(resolved.get("inputs"), "resolved inputs")
    override_sha = inputs.get("override_sha256")
    if override_sha is not None:
        override_sha = required_sha(override_sha, "override patch")
    return {
        "project_id": project_id,
        "canvas": canvas,
        "layer_manifest_sha256": layer_sha,
        "resolved_project_sha256": resolved_sha,
        "override_patch_sha256": override_sha,
    }


def review_gate(
    manifest: Mapping[str, Any], resolved: Mapping[str, Any], allow: bool
) -> bool:
    issues = review_issues(manifest, resolved)
    if issues and not allow:
        raise RegionRigContractError("Rig compile inputs require manual review")
    return bool(issues)


def review_issues(
    manifest: Mapping[str, Any], resolved: Mapping[str, Any]
) -> list[str]:
    """Return every condition that keeps otherwise valid P2 inputs diagnostic."""

    statuses = [_qa_status(manifest.get("qa"), "Layer Manifest")]
    layers = manifest.get("layers")
    if not isinstance(layers, list):
        raise RegionRigContractError("Layer Manifest layers must be an array")
    issues: list[str] = []
    for index, layer in enumerate(layers):
        layer = mapping(layer, f"layer {index}")
        layer_id = layer.get("layer_id")
        label = layer_id if isinstance(layer_id, str) else str(index)
        layer_status = _qa_status(layer.get("qa"), f"layer {index}")
        statuses.append(layer_status)
        if layer_status == "manual_required":
            issues.append(f"layer {label} QA requires review")
        hint = mapping(layer.get("rig_hint"), f"layer {index} rig hint")
        if hint.get("attachment_kind") != "region":
            continue
        semantic = mapping(layer.get("semantic"), f"layer {index} semantic")
        pivot = hint.get("pivot")
        if semantic.get("mapping_method") != "manual":
            issues.append(f"layer {label} semantic mapping is not manual")
        if not isinstance(pivot, Mapping) or pivot.get("method") != "manual":
            issues.append(f"layer {label} pivot is not manually reviewed")
        if hint.get("candidate_bone") is None:
            issues.append(f"layer {label} bone binding requires review")
    if "rejected" in statuses:
        raise RegionRigContractError("Rejected Layer Manifest data cannot be compiled")
    if statuses[0] == "manual_required":
        issues.append("layer manifest QA requires review")
    resolved_qa = mapping(resolved.get("qa"), "resolved project QA")
    resolved_status = resolved_qa.get("status")
    if resolved_status not in {"ready", "needs_review"}:
        raise RegionRigContractError("Resolved project QA status is invalid")
    if resolved_status != "ready":
        issues.append("resolved project still requires review")
    return sorted(set(issues))


def mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RegionRigContractError(f"{label} must be an object")
    return value


def required_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise RegionRigContractError(f"{label} SHA-256 is invalid")
    return value


def point(value: Any, label: str) -> list[int | float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2 or not all(is_finite(item) for item in value):
        raise RegionRigContractError(f"{label} must contain two finite numbers")
    return list(value)


def positive_size(value: Any, label: str) -> list[int]:
    if not isinstance(value, (list, tuple)) or len(value) != 2 or not all(
        is_integer(item) and item > 0 for item in value
    ):
        raise RegionRigContractError(f"{label} must contain two positive integers")
    return list(value)


def safe_image_path(value: Any, layer_id: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise RegionRigContractError(f"Layer {layer_id} image path is unsafe")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or path.parts[0] != "layers" or any(
        part in {"", ".", ".."} or ":" in part for part in path.parts
    ):
        raise RegionRigContractError(f"Layer {layer_id} image path is unsafe")
    return value


def is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _qa_status(value: Any, label: str) -> str:
    qa = mapping(value, f"{label} QA")
    status = qa.get("status")
    if status not in {"passed", "manual_required", "rejected"}:
        raise RegionRigContractError(f"{label} QA status is invalid")
    return status


def _canonical(value: Any, label: str) -> str:
    try:
        return canonical_sha256(value)
    except (TypeError, ValueError) as exc:
        raise RegionRigContractError(f"{label} is not canonical JSON data") from exc
