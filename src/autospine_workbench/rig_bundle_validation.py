"""Strict input and asset validation for immutable RigIR bundles."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping

from .layer_manifest import sha256_file
from .resolved_project import canonical_sha256
from .rig_artifact_validation import (
    RigArtifactValidationError,
    require_compile_run_document,
    require_region_rig_profile,
    require_setup_probe_document,
)
from .rig_validation import RigSemanticValidationError, RigSemanticValidator


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class RigBundleError(RuntimeError):
    """Raised when a RigIR bundle cannot be published losslessly."""


def validate_bundle_inputs(
    project_id: str,
    rig: Mapping[str, Any],
    run: Mapping[str, Any],
    probes: Mapping[str, Any],
    layer_bundle_path: Path,
) -> tuple[str, dict[str, tuple[Path, str]]]:
    if not isinstance(project_id, str) or not _SAFE_ID.fullmatch(project_id):
        raise RigBundleError("Project id is unsafe")
    if not all(isinstance(value, Mapping) for value in (rig, run, probes)):
        raise RigBundleError("RigIR bundle documents must be objects")
    if rig.get("format") != "autospine-rig-ir" or rig.get("format_version") != 1:
        raise RigBundleError("Unsupported RigIR document")
    try:
        RigSemanticValidator().raise_for_errors(rig)
        require_region_rig_profile(rig)
        require_compile_run_document(run)
        require_setup_probe_document(probes)
        rig_sha = canonical_sha256(rig)
        run_sha = canonical_sha256(run)
        canonical_sha256(probes)
    except (RigArtifactValidationError, RigSemanticValidationError, TypeError, ValueError) as exc:
        raise RigBundleError("RigIR bundle documents are not valid canonical JSON") from exc

    rig_source = _mapping(rig.get("source"), "RigIR source")
    layer_sha = required_sha(rig_source.get("layer_manifest_sha256"), "layer manifest")
    if required_sha(rig_source.get("run_manifest_sha256"), "run manifest") != run_sha:
        raise RigBundleError("RigIR run manifest binding is incorrect")
    _validate_run(project_id, run, layer_sha, rig_source)
    _validate_probes(project_id, probes, rig_sha, layer_sha, run)
    if (rig.get("qa") or {}).get("status") != probes.get("status"):
        raise RigBundleError("RigIR and setup probe QA status differ")
    if probes.get("status") == "manual_required" and not run["compiler"]["config"][
        "allow_manual_required"
    ]:
        raise RigBundleError("Manual-required setup was not enabled by the compile run")
    bundle = _resolve_layer_bundle(layer_bundle_path)
    manifest_assets = _manifest_assets(project_id, bundle, layer_sha)
    return rig_sha, _attachment_assets(rig, manifest_assets, bundle)


def _validate_run(
    project_id: str,
    run: Mapping[str, Any],
    layer_sha: str,
    rig_source: Mapping[str, Any],
) -> None:
    if run.get("project_id") != project_id:
        raise RigBundleError("Compile run manifest identity is invalid")
    inputs = _mapping(run.get("inputs"), "compile run inputs")
    if required_sha(inputs.get("layer_manifest_sha256"), "run layer manifest") != layer_sha:
        raise RigBundleError("Compile run references another layer manifest")
    required_sha(inputs.get("resolved_project_sha256"), "resolved project")
    run_override = inputs.get("override_patch_sha256")
    rig_override = rig_source.get("override_patch_sha256")
    if run_override is not None:
        run_override = required_sha(run_override, "run override patch")
    if rig_override is not None:
        rig_override = required_sha(rig_override, "RigIR override patch")
    if run_override != rig_override:
        raise RigBundleError("RigIR override patch binding is incorrect")


def _validate_probes(
    project_id: str,
    probes: Mapping[str, Any],
    rig_sha: str,
    layer_sha: str,
    run: Mapping[str, Any],
) -> None:
    if probes.get("project_id") != project_id:
        raise RigBundleError("Setup probe report identity is invalid")
    source = _mapping(probes.get("source"), "probe source")
    expected = {
        "rig_sha256": rig_sha,
        "layer_manifest_sha256": layer_sha,
        "resolved_project_sha256": run["inputs"]["resolved_project_sha256"],
    }
    for field, value in expected.items():
        if required_sha(source.get(field), f"probe {field}") != value:
            raise RigBundleError(f"Probe report {field} binding is incorrect")


def _resolve_layer_bundle(lexical: Path) -> Path:
    lexical = Path(lexical)
    for path in (lexical, lexical.parent, lexical.parent.parent):
        if path.is_symlink():
            raise RigBundleError("Layer Manifest bundle path contains a symlink")
    try:
        bundle = lexical.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise RigBundleError("Layer Manifest bundle does not exist") from exc
    if not bundle.is_dir():
        raise RigBundleError("Layer Manifest bundle is not a directory")
    return bundle


def _manifest_assets(
    project_id: str, bundle: Path, expected_sha: str
) -> dict[str, tuple[str, str]]:
    manifest = read_json(bundle / "manifest.json")
    if canonical_sha256(manifest) != expected_sha or manifest.get("project_id") != project_id:
        raise RigBundleError("Layer Manifest document binding is incorrect")
    result: dict[str, tuple[str, str]] = {}
    layers = manifest.get("layers")
    if not isinstance(layers, list):
        raise RigBundleError("Layer Manifest layers must be an array")
    for layer in layers:
        try:
            layer_id = str(layer["layer_id"])
            relative = safe_relative(layer["raster"]["artifact_path"])
            digest = required_sha(layer["raster"]["sha256"], f"layer {layer_id}")
        except (KeyError, TypeError) as exc:
            raise RigBundleError("Layer Manifest raster entry is incomplete") from exc
        if relative in result or not _SAFE_ID.fullmatch(layer_id):
            raise RigBundleError("Layer Manifest raster identity is unsafe or duplicated")
        source = safe_existing_file(bundle, relative)
        require_png(source)
        if sha256_file(source) != digest:
            raise RigBundleError(f"Layer Manifest bundle hash mismatch: {layer_id}")
        result[relative] = (layer_id, digest)
    return result


def _attachment_assets(
    rig: Mapping[str, Any],
    manifest_assets: Mapping[str, tuple[str, str]],
    layer_bundle: Path,
) -> dict[str, tuple[Path, str]]:
    attachments = rig.get("attachments")
    if not isinstance(attachments, list):
        raise RigBundleError("RigIR attachments must be an array")
    assets: dict[str, tuple[Path, str]] = {}
    known_layers = {value[0] for value in manifest_assets.values()}
    for attachment in attachments:
        if not isinstance(attachment, Mapping) or attachment.get("type") != "region":
            continue
        relative = safe_relative(attachment.get("image_path"))
        if relative not in manifest_assets:
            raise RigBundleError("Region image is not in the Layer Manifest bundle")
        layer_id, expected_sha = manifest_assets[relative]
        if required_sha(attachment.get("image_sha256"), "region image") != expected_sha:
            raise RigBundleError("Region image hash does not match the Layer Manifest")
        source_ids = attachment.get("source_layer_ids")
        if (
            not isinstance(source_ids, list)
            or layer_id not in source_ids
            or any(item not in known_layers for item in source_ids)
        ):
            raise RigBundleError("Region source layers do not match the Layer Manifest")
        assets[relative] = (safe_existing_file(layer_bundle, relative), expected_sha)
    return dict(sorted(assets.items()))


def safe_relative(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise RigBundleError("Region image path is not a safe relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or path.parts[0] != "layers" or any(
        part in {"", ".", ".."} or ":" in part for part in path.parts
    ):
        raise RigBundleError("Region image path is not a safe relative path")
    return path.as_posix()


def safe_existing_file(root: Path, relative: str) -> Path:
    current = root
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink():
            raise RigBundleError("Layer path contains a symlink")
    try:
        resolved_root = root.resolve(strict=True)
        resolved = current.resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise RigBundleError("Layer path escapes or is missing from its bundle") from exc
    if not resolved.is_file():
        raise RigBundleError("Layer path is not a regular file")
    return resolved


def read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise RigBundleError(f"JSON document cannot be a symlink: {path.name}")
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle, object_pairs_hook=_unique_object, parse_constant=_bad_constant)
    except RigBundleError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RigBundleError(f"Cannot read strict JSON document: {path.name}") from exc
    if not isinstance(value, dict):
        raise RigBundleError(f"JSON document must be an object: {path.name}")
    return value


def required_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise RigBundleError(f"{label} SHA-256 is invalid")
    return value


def require_png(path: Path) -> None:
    try:
        with path.open("rb") as handle:
            if handle.read(8) != _PNG_SIGNATURE:
                raise RigBundleError(f"Not a PNG file: {path.name}")
    except OSError as exc:
        raise RigBundleError(f"Cannot inspect PNG: {path.name}") from exc


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RigBundleError(f"{label} must be an object")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RigBundleError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def _bad_constant(value: str) -> None:
    raise RigBundleError(f"Non-finite JSON constant: {value}")
