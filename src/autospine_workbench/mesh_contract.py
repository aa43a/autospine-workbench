"""Strict, version-neutral P3 mesh compile-run identity contracts."""

from __future__ import annotations

import re
from typing import Any, Mapping

from .resolved_project import canonical_sha256
from .rig_artifact_validation import (
    RigArtifactValidationError,
    require_compile_run_document,
    require_region_rig_profile,
)
from .rig_validation import RigSemanticValidationError, RigSemanticValidator


MESH_RUN_FORMAT = "autospine-mesh-rig-compile-run"
MESH_RUN_FORMAT_VERSION = 1
MESH_COMPILER_ID = "mesh-rig-compiler"
MESH_COMPILER_VERSION = "1.0.0"
MESH_PROFILE = "hinge-alpha-grid-two-bone-v1"

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_BASE_RIG_FIELDS = {
    "format",
    "format_version",
    "source",
    "canvas",
    "capabilities",
    "unsupported_feature_policy",
    "bones",
    "slots",
    "attachments",
    "skins",
    "animations",
    "qa",
}


class MeshContractError(ValueError):
    """Raised when P3 provenance or its reviewed P2 base is unsupported."""


def mesh_compile_config() -> dict[str, Any]:
    """Return a fresh copy of the only supported P3 mesh compiler profile."""

    return {
        "profile": MESH_PROFILE,
        "strict": True,
        "alpha_threshold": 8,
        "grid_step_px": 8,
        "blend_fraction": 0.20,
        "weight_quantization": "uint16-65535",
        "resource_limits": {
            "attachment_max_vertices": 4096,
            "attachment_max_triangles": 8192,
            "rig_max_vertices": 32768,
            "rig_max_triangles": 65536,
        },
        "geometry_contract": {
            "vertex_space": "source-raster-edge-px",
            "setup_world": "canvas-offset-plus-vertex",
            "uv_space": "normalized-top-left",
            "triangle_winding": "clockwise-canvas-y-down",
            "skinning": "linear-blend-inverse-setup-v1",
        },
    }


def require_base_region_rig(
    rig: Mapping[str, Any], run: Mapping[str, Any]
) -> dict[str, str]:
    """Validate and identify a reviewed, exact P2 region-only compilation."""

    rig = _mapping(rig, "base RigIR")
    run = _mapping(run, "base compile run")
    _exact(rig, _BASE_RIG_FIELDS, "base RigIR")
    if rig.get("format") != "autospine-rig-ir" or not _integer_equal(
        rig.get("format_version"), 1
    ):
        raise MeshContractError("Base RigIR format is unsupported")
    _require_base_source_and_canvas(rig)
    try:
        RigSemanticValidator().raise_for_errors(rig)
        require_region_rig_profile(rig)
        require_compile_run_document(run)
        rig_sha = canonical_sha256(rig)
        run_sha = canonical_sha256(run)
    except (
        RigArtifactValidationError,
        RigSemanticValidationError,
        TypeError,
        ValueError,
    ) as exc:
        raise MeshContractError("Base P2 region-only documents are invalid") from exc
    if (rig.get("qa") or {}).get("status") != "passed":
        raise MeshContractError("Base RigIR QA must be passed")
    config = _mapping(run["compiler"].get("config"), "base compile config")
    if config.get("allow_manual_required") is not False:
        raise MeshContractError("Base P2 compile run must be strictly reviewed")
    project_id = _safe_id(run.get("project_id"), "base project id")
    source = _mapping(rig.get("source"), "base RigIR source")
    inputs = _mapping(run.get("inputs"), "base compile inputs")
    if source.get("run_manifest_sha256") != run_sha:
        raise MeshContractError("Base RigIR run manifest binding is invalid")
    layer_sha = _sha(inputs.get("layer_manifest_sha256"), "base layer manifest")
    if source.get("layer_manifest_sha256") != layer_sha:
        raise MeshContractError("Base RigIR layer manifest binding is invalid")
    resolved_sha = _sha(inputs.get("resolved_project_sha256"), "base resolved project")
    if source.get("override_patch_sha256") != inputs.get("override_patch_sha256"):
        raise MeshContractError("Base RigIR override binding is invalid")
    return {
        "project_id": project_id,
        "base_rig_sha256": rig_sha,
        "base_run_manifest_sha256": run_sha,
        "layer_manifest_sha256": layer_sha,
        "resolved_project_sha256": resolved_sha,
    }


def build_mesh_compile_run(
    base_rig: Mapping[str, Any],
    base_run: Mapping[str, Any],
    *,
    base_bundle_sha256: str,
) -> dict[str, Any]:
    """Build deterministic P3 provenance without modifying the P2 documents."""

    identity = require_base_region_rig(base_rig, base_run)
    result = {
        "format": MESH_RUN_FORMAT,
        "format_version": MESH_RUN_FORMAT_VERSION,
        "project_id": identity["project_id"],
        "inputs": {
            "base_rig_sha256": identity["base_rig_sha256"],
            "base_bundle_sha256": _sha(base_bundle_sha256, "base bundle"),
            "layer_manifest_sha256": identity["layer_manifest_sha256"],
            "resolved_project_sha256": identity["resolved_project_sha256"],
        },
        "compiler": {
            "id": MESH_COMPILER_ID,
            "version": MESH_COMPILER_VERSION,
            "config": mesh_compile_config(),
        },
    }
    require_mesh_compile_run(result)
    return result


def require_mesh_compile_run(
    document: Mapping[str, Any],
    *,
    base_rig: Mapping[str, Any] | None = None,
    base_run: Mapping[str, Any] | None = None,
) -> None:
    """Fail closed unless a document is the exact current P3 compile profile."""

    document = _mapping(document, "mesh compile run")
    _exact(
        document,
        {"format", "format_version", "project_id", "inputs", "compiler"},
        "mesh compile run",
    )
    if document.get("format") != MESH_RUN_FORMAT or not _integer_equal(
        document.get("format_version"), MESH_RUN_FORMAT_VERSION
    ):
        raise MeshContractError("Mesh compile run format is unsupported")
    project_id = _safe_id(document.get("project_id"), "mesh project id")
    inputs = _mapping(document.get("inputs"), "mesh compile inputs")
    _exact(
        inputs,
        {
            "base_rig_sha256",
            "base_bundle_sha256",
            "layer_manifest_sha256",
            "resolved_project_sha256",
        },
        "mesh compile inputs",
    )
    for field in inputs:
        _sha(inputs.get(field), field.replace("_", " "))
    compiler = _mapping(document.get("compiler"), "mesh compiler")
    _exact(compiler, {"id", "version", "config"}, "mesh compiler")
    if (
        compiler.get("id") != MESH_COMPILER_ID
        or compiler.get("version") != MESH_COMPILER_VERSION
    ):
        raise MeshContractError("Mesh compiler identity is unsupported")
    config = _mapping(compiler.get("config"), "mesh compiler config")
    _require_pinned_config(config)
    if (base_rig is None) != (base_run is None):
        raise MeshContractError("Base RigIR and compile run must be supplied together")
    if base_rig is not None and base_run is not None:
        identity = require_base_region_rig(base_rig, base_run)
        expected = {
            "base_rig_sha256": identity["base_rig_sha256"],
            "layer_manifest_sha256": identity["layer_manifest_sha256"],
            "resolved_project_sha256": identity["resolved_project_sha256"],
        }
        if document.get("project_id") != identity["project_id"]:
            raise MeshContractError("Mesh project differs from its base RigIR")
        for field, value in expected.items():
            if inputs.get(field) != value:
                label = "base RigIR" if field == "base_rig_sha256" else "base inputs"
                raise MeshContractError(f"Mesh compile run {label} binding is invalid")


def mesh_compile_run_sha256(document: Mapping[str, Any]) -> str:
    """Return the canonical address of a valid P3 compile-run document."""

    require_mesh_compile_run(document)
    try:
        return canonical_sha256(document)
    except (TypeError, ValueError) as exc:  # pragma: no cover - validation is stricter
        raise MeshContractError("Mesh compile run is not canonical JSON") from exc


def _require_base_source_and_canvas(rig: Mapping[str, Any]) -> None:
    source = _mapping(rig.get("source"), "base RigIR source")
    keys = set(source)
    required = {"run_manifest_sha256", "layer_manifest_sha256"}
    if not required.issubset(keys) or not keys.issubset(
        required | {"override_patch_sha256"}
    ):
        raise MeshContractError("Base RigIR source fields are unsupported")
    for field in keys:
        _sha(source.get(field), f"base {field}")
    canvas = _mapping(rig.get("canvas"), "base RigIR canvas")
    _exact(
        canvas,
        {"width", "height", "origin", "x_axis", "y_axis", "units"},
        "base RigIR canvas",
    )
    if any(
        not isinstance(canvas.get(field), int)
        or isinstance(canvas.get(field), bool)
        or canvas[field] < 1
        for field in ("width", "height")
    ) or {
        "origin": canvas.get("origin"),
        "x_axis": canvas.get("x_axis"),
        "y_axis": canvas.get("y_axis"),
        "units": canvas.get("units"),
    } != {"origin": "top_left", "x_axis": "right", "y_axis": "down", "units": "pixel"}:
        raise MeshContractError("Base RigIR canvas contract is unsupported")


def _require_pinned_config(config: Mapping[str, Any]) -> None:
    expected = mesh_compile_config()
    try:
        matches = canonical_sha256(config) == canonical_sha256(expected)
    except (TypeError, ValueError) as exc:
        raise MeshContractError("Mesh compiler config is not canonical JSON") from exc
    if not matches:
        raise MeshContractError("Mesh compiler profile, thresholds, or geometry changed")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MeshContractError(f"{label} must be an object")
    return value


def _exact(value: Mapping[str, Any], keys: set[str], label: str) -> None:
    if set(value) != keys:
        raise MeshContractError(f"{label} fields are incomplete or unsupported")


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise MeshContractError(f"{label} is invalid")
    return value


def _sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise MeshContractError(f"{label} SHA-256 is invalid")
    return value


def _integer_equal(value: Any, expected: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == expected
