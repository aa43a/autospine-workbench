"""CLI orchestration for exact P3 mesh compilation and verification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .mesh_bundle_reader import (
    VerifiedMeshBundleReader,
    VerifiedMeshBundleReaderError,
)
from .mesh_bundle_store import MeshBundleStore, MeshBundleStoreError
from .mesh_pipeline import VerifiedMeshPipeline, VerifiedMeshPipelineError


class MeshCommandError(RuntimeError):
    """Raised when adjacent P3 stages disagree on an immutable identity."""


def add_mesh_subcommands(subparsers: Any, *, default_state_root: Path) -> None:
    compile_parser = subparsers.add_parser(
        "compile-mesh-rig",
        help="Compile, publish, and fully verify one exact P3 mesh bundle",
    )
    _identity_arguments(compile_parser, default_state_root, include_base=True)
    verify_parser = subparsers.add_parser(
        "verify-mesh-bundle",
        help="Read-only verification of one exact P3 mesh bundle address",
    )
    _identity_arguments(verify_parser, default_state_root, include_base=False)


def compile_mesh_rig_command(
    project_id: str,
    state_root: Path,
    *,
    base_rig_sha256: str,
    base_bundle_sha256: str,
) -> int:
    """Run the verified pipeline, immutable publication, and full read-back gate."""
    try:
        pipeline = VerifiedMeshPipeline(state_root).build(
            project_id, base_rig_sha256, base_bundle_sha256
        )
        inputs, outputs = pipeline.input_sha256s, pipeline.output_sha256s
        _require_pipeline_identity(
            pipeline, inputs, outputs, project_id, base_rig_sha256, base_bundle_sha256
        )
        published = MeshBundleStore(state_root).publish(
            project_id,
            pipeline.rig,
            pipeline.run_manifest,
            pipeline.probes,
            pipeline.visuals,
            pipeline.pngs,
        )
        if (
            published.rig_sha256 != outputs["rig_sha256"]
            or published.bundle_sha256 == ""
        ):
            raise MeshCommandError("Published mesh bundle identity differs from the pipeline")
        verified = _load_verified_bundle(
            state_root, project_id, published.rig_sha256, published.bundle_sha256
        )
        _require_verified_identity(
            verified,
            project_id=project_id,
            base_rig_sha256=base_rig_sha256,
            base_bundle_sha256=base_bundle_sha256,
            layer_manifest_sha256=inputs["layer_manifest_sha256"],
            resolved_project_sha256=inputs["resolved_project_sha256"],
            rig_sha256=outputs["rig_sha256"],
            run_sha256=outputs["run_manifest_sha256"],
            probes_sha256=outputs["probes_sha256"],
            visuals_sha256=outputs["visuals_sha256"],
            bundle_sha256=published.bundle_sha256,
            path=published.path,
        )
        if _verified_summary(verified) != pipeline.summary:
            raise MeshCommandError("Verified mesh bundle summary differs from the pipeline")
        response = _verified_response(verified)
        response.update(ok=True, status="passed", summary=pipeline.summary)
    except _DOMAIN_ERRORS as exc:
        _print({"ok": False, "status": "error", "error": str(exc)})
        return 2
    _print(response)
    return 0


def verify_mesh_bundle_command(
    project_id: str,
    state_root: Path,
    *,
    rig_sha256: str,
    bundle_sha256: str,
) -> int:
    """Verify an explicitly addressed bundle without discovering or writing state."""
    try:
        verified = _load_verified_bundle(
            state_root, project_id, rig_sha256, bundle_sha256
        )
        _require_verified_identity(
            verified,
            project_id=project_id,
            rig_sha256=rig_sha256,
            bundle_sha256=bundle_sha256,
        )
        response = _verified_response(verified)
        response.update(ok=True, status="passed")
    except _DOMAIN_ERRORS as exc:
        _print({"ok": False, "status": "error", "error": str(exc)})
        return 2
    _print(response)
    return 0


def _load_verified_bundle(state_root, project_id, rig_sha256, bundle_sha256):
    return VerifiedMeshBundleReader(state_root).load(
        project_id, rig_sha256, bundle_sha256
    )


def _require_pipeline_identity(pipeline, inputs, outputs, project, base_rig, base_bundle):
    if not isinstance(inputs, dict) or not isinstance(outputs, dict):
        raise MeshCommandError("Mesh pipeline identities must be objects")
    expected_inputs = {
        "base_rig_sha256": base_rig,
        "base_bundle_sha256": base_bundle,
    }
    if pipeline.project_id != project or any(inputs.get(k) != v for k, v in expected_inputs.items()):
        raise MeshCommandError("Mesh pipeline input identity differs from the request")
    required_outputs = {
        "rig_sha256", "run_manifest_sha256", "probes_sha256", "visuals_sha256"
    }
    required_inputs = {
        "layer_manifest_sha256", "resolved_project_sha256",
    }
    if not required_outputs.issubset(outputs) or not required_inputs.issubset(inputs):
        raise MeshCommandError("Mesh pipeline identities are incomplete")


def _require_verified_identity(verified, **expected) -> None:
    aliases = {"path": "path"}
    for name, value in expected.items():
        actual = getattr(verified, aliases.get(name, name), None)
        if name == "path":
            actual = Path(actual).resolve() if actual is not None else None
            value = Path(value).resolve()
        if actual != value:
            raise MeshCommandError(f"Verified mesh bundle {name} differs from the request")


def _verified_response(verified) -> dict[str, Any]:
    return {
        "project_id": verified.project_id,
        "base_rig_sha256": verified.base_rig_sha256,
        "base_bundle_sha256": verified.base_bundle_sha256,
        "layer_manifest_sha256": verified.layer_manifest_sha256,
        "resolved_project_sha256": verified.resolved_project_sha256,
        "rig_sha256": verified.rig_sha256,
        "run_manifest_sha256": verified.run_sha256,
        "probes_sha256": verified.probes_sha256,
        "visuals_sha256": verified.visuals_sha256,
        "bundle_sha256": verified.bundle_sha256,
        "bundle_path": str(verified.path),
        "summary": _verified_summary(verified),
    }


def _verified_summary(verified) -> str:
    visuals = verified.visuals
    summary = visuals.get("summary") if isinstance(visuals, dict) else None
    if summary != "reviewed-noop" and not (
        isinstance(summary, str) and summary.startswith("converted=")
        and summary.removeprefix("converted=").isdigit()
    ):
        raise MeshCommandError("Verified mesh bundle summary is invalid")
    return summary


def _identity_arguments(parser: argparse.ArgumentParser, state_root: Path,
                        *, include_base: bool) -> None:
    parser.add_argument("project_id", help="Audit project identifier")
    if include_base:
        parser.add_argument("--base-rig-sha256", required=True)
        parser.add_argument("--base-bundle-sha256", required=True)
    else:
        parser.add_argument("--rig-sha256", required=True)
        parser.add_argument("--bundle-sha256", required=True)
    parser.add_argument("--state-root", type=Path, default=state_root)


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


_DOMAIN_ERRORS = (
    MeshCommandError,
    MeshBundleStoreError,
    VerifiedMeshPipelineError,
    VerifiedMeshBundleReaderError,
)
