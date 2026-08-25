"""Deterministic, fail-closed setup probes for region-only RigIR builds."""

from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .resolved_project import canonical_sha256
from .rig_fk import RigFkError, evaluate_world_setup
from .rig_setup_probe_regions import region_layers, run_region_checks
from .rig_setup_render import RigSetupRenderError, compare_region_setup


RUNNER = {"id": "rig-setup-probes", "version": "1.0.0"}
TOLERANCE = 1e-6


def run_setup_probes(
    rig: Mapping[str, Any],
    manifest: Mapping[str, Any],
    resolved: Mapping[str, Any],
    *,
    rig_sha256: str,
    bundle_path: Path | None = None,
) -> dict[str, Any]:
    """Return a stable report; all discovered problems are explicit checks."""

    rig_source = rig.get("source") if isinstance(rig, Mapping) else {}
    layer_sha = _text((rig_source or {}).get("layer_manifest_sha256"))
    resolved_sha = _text(resolved.get("sha256")) if isinstance(resolved, Mapping) else ""
    project_id = _text(resolved.get("project_id")) or _text(manifest.get("project_id"))
    checks = [
        _source_check(rig, manifest, resolved, rig_sha256, project_id, layer_sha, resolved_sha),
        _review_check(manifest, resolved),
        _parent_check(rig, resolved),
        _fk_check(rig, resolved),
        *run_region_checks(rig, manifest),
    ]
    if bundle_path is not None:
        checks.append(_pixel_check(rig, manifest, bundle_path))
    return {
        "format": "autospine-rig-setup-probes",
        "format_version": 1,
        "project_id": project_id,
        "source": {
            "rig_sha256": _text(rig_sha256),
            "layer_manifest_sha256": layer_sha,
            "resolved_project_sha256": resolved_sha,
        },
        "runner": dict(RUNNER),
        "status": _aggregate_status(checks),
        "checks": checks,
    }


def _source_check(
    rig: Mapping[str, Any],
    manifest: Mapping[str, Any],
    resolved: Mapping[str, Any],
    rig_sha: str,
    project_id: str,
    layer_sha: str,
    resolved_sha: str,
) -> dict[str, Any]:
    errors: list[str] = []
    manifest_project = _text(manifest.get("project_id"))
    resolved_project = _text(resolved.get("project_id"))
    if not project_id or manifest_project != project_id or resolved_project != project_id:
        errors.append("manifest and resolved project ids do not match")
    expected = (
        ("rig", _text(rig_sha), canonical_sha256(rig)),
        ("layer manifest", layer_sha, canonical_sha256(manifest)),
        ("resolved project", resolved_sha, _resolved_sha(resolved)),
    )
    for label, claimed, actual in expected:
        if not _is_sha(claimed):
            errors.append(f"{label} SHA-256 is invalid")
        elif claimed != actual:
            errors.append(f"{label} SHA-256 does not match content")
    return _check("source.identity", errors, metrics={"project_id": project_id})


def _review_check(manifest: Mapping[str, Any], resolved: Mapping[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    if _text((manifest.get("qa") or {}).get("status")) != "passed":
        warnings.append("layer manifest QA is not passed")
    if _text((resolved.get("qa") or {}).get("status")) != "ready":
        warnings.append("resolved project still requires review")
    reviewed_regions = region_layers(manifest)
    for layer_id, layer in reviewed_regions.items():
        semantic = layer.get("semantic") or {}
        pivot = (layer.get("rig_hint") or {}).get("pivot")
        if semantic.get("mapping_method") != "manual":
            warnings.append(f"layer {layer_id} semantic mapping is not manual")
        if not isinstance(pivot, Mapping) or pivot.get("method") != "manual":
            warnings.append(f"layer {layer_id} pivot is not manually reviewed")
    status = "manual_required" if warnings else "passed"
    return _check("inputs.reviewed", warnings, status=status, metrics={"region_count": len(reviewed_regions)})


def _parent_check(rig: Mapping[str, Any], resolved: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    rig_bones = _by_id(rig.get("bones"), "rig bone", errors)
    skeleton = resolved.get("skeleton") if isinstance(resolved, Mapping) else {}
    source_bones = _by_id((skeleton or {}).get("bones"), "source bone", errors)
    if set(rig_bones) != set(source_bones):
        errors.append("rig bone ids do not exactly match the source skeleton")
    for bone_id in sorted(set(rig_bones) & set(source_bones)):
        if rig_bones[bone_id].get("parent") != source_bones[bone_id].get("parent_id"):
            errors.append(f"bone {bone_id} parent does not match source")
    return _check("bones.parent-links", errors, metrics={"bone_count": len(rig_bones)})


def _fk_check(rig: Mapping[str, Any], resolved: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    origin_errors: list[float] = []
    endpoint_errors: list[float] = []
    try:
        worlds = evaluate_world_setup(rig.get("bones"))
        skeleton = resolved.get("skeleton") or {}
        joints = _by_id(skeleton.get("joints"), "joint", errors)
        sources = _by_id(skeleton.get("bones"), "source bone", errors)
        for bone_id, source in sorted(sources.items()):
            world = worlds.get(bone_id)
            start, end = joints.get(source.get("start_joint_id")), joints.get(source.get("end_joint_id"))
            if world is None or start is None or end is None:
                errors.append(f"bone {bone_id} cannot be compared with resolved joints")
                continue
            origin_errors.append(_distance(world["origin_xy"], [start.get("x"), start.get("y")]))
            endpoint_errors.append(_distance(world["endpoint_xy"], [end.get("x"), end.get("y")]))
    except (RigFkError, TypeError, ValueError) as exc:
        errors.append(f"FK evaluation failed: {exc}")
    max_origin = max(origin_errors, default=0.0)
    max_endpoint = max(endpoint_errors, default=0.0)
    if max_origin > TOLERANCE:
        errors.append("FK world origins do not reconstruct resolved joints")
    if max_endpoint > TOLERANCE:
        errors.append("FK world endpoints do not reconstruct resolved joints")
    return _check(
        "fk.setup-reconstruction",
        errors,
        metrics={
            "compared_bones": len(origin_errors),
            "max_origin_error_px": max_origin,
            "max_endpoint_error_px": max_endpoint,
        },
    )


def _pixel_check(
    rig: Mapping[str, Any], manifest: Mapping[str, Any], bundle_path: Path
) -> dict[str, Any]:
    try:
        comparison = compare_region_setup(manifest, rig, bundle_path)
    except (RigSetupRenderError, OSError, ValueError) as exc:
        return _check(
            "setup.pixel-reconstruction",
            [f"setup pixels could not be reconstructed: {exc}"],
            metrics={"exact": False},
        )
    metrics = comparison.to_dict()
    return _check(
        "setup.pixel-reconstruction",
        [] if comparison.exact else ["RigIR setup pixels differ from Layer Manifest"],
        metrics=metrics,
    )


def _by_id(value: Any, label: str, errors: list[str]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for item in _objects(value):
        item_id = _text(item.get("id"))
        if not item_id:
            errors.append(f"{label} has an invalid id")
        elif item_id in result:
            errors.append(f"duplicate {label} id: {item_id}")
        else:
            result[item_id] = item
    return result


def _objects(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _distance(first: Any, second: Any) -> float:
    if not isinstance(first, Sequence) or not isinstance(second, Sequence) or len(first) != 2 or len(second) != 2:
        raise ValueError("point must contain two numbers")
    values = [first[0], first[1], second[0], second[1]]
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
        raise ValueError("point must contain finite numbers")
    if any(not math.isfinite(float(value)) for value in values):
        raise ValueError("point must contain finite numbers")
    return math.hypot(float(first[0]) - float(second[0]), float(first[1]) - float(second[1]))


def _resolved_sha(resolved: Mapping[str, Any]) -> str:
    payload = deepcopy(dict(resolved))
    payload.pop("sha256", None)
    return canonical_sha256(payload)


def _check(
    check_id: str,
    messages: Sequence[str],
    *,
    status: str | None = None,
    metrics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    unique = sorted(set(messages))
    result: dict[str, Any] = {"id": check_id, "status": status or ("rejected" if unique else "passed")}
    if unique:
        result["message"] = "; ".join(unique)
    if metrics is not None:
        result["metrics"] = dict(metrics)
    return result


def _aggregate_status(checks: Sequence[Mapping[str, Any]]) -> str:
    statuses = {check.get("status") for check in checks}
    if "rejected" in statuses:
        return "rejected"
    if "manual_required" in statuses:
        return "manual_required"
    return "passed"


def _is_sha(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""
