"""CLI orchestration for deterministic P2 RigIR compilation and probes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .manifest_bundle import LayerManifestBundleError, LayerManifestBundleReader
from .project_store import ProjectNotFoundError, ProjectStateError, ProjectStore
from .region_rig import RegionRigError, compile_region_rig
from .resolved_project import canonical_sha256
from .rig_bundle import RigBundleError, RigBundleStore
from .rig_bundle_validation import read_json
from .rig_setup_probes import run_setup_probes


def add_rig_subcommands(
    subparsers: Any, *, default_workspace: Path, default_state_root: Path
) -> None:
    compile_parser = subparsers.add_parser(
        "compile-rig",
        help="Compile and publish one pinned region-only RigIR setup bundle",
    )
    _project_arguments(compile_parser, default_workspace, default_state_root)
    compile_parser.add_argument(
        "--allow-manual-required",
        action="store_true",
        help="Publish a diagnostic bundle while preserving manual-required QA",
    )

    probes = subparsers.add_parser(
        "run-probes",
        help="Run deterministic setup probes for one RigIR JSON document",
    )
    _project_arguments(probes, default_workspace, default_state_root)
    probes.add_argument("rig", type=Path, help="RigIR JSON document to probe")


def compile_rig_command(
    project_id: str,
    workspace: Path,
    state_root: Path,
    *,
    layer_manifest_sha256: str,
    allow_manual_required: bool = False,
) -> int:
    try:
        project = _project_store(workspace, state_root).get_project(project_id)
        resolved = _resolved(project)
        bundle = LayerManifestBundleReader(state_root).load(
            project_id, layer_manifest_sha256
        )
        compilation = compile_region_rig(
            bundle.manifest,
            resolved,
            layer_manifest_sha256=bundle.sha256,
            image_sizes=bundle.image_sizes,
            allow_manual_required=allow_manual_required,
        )
        rig, run_manifest = compilation.rig, compilation.run_manifest
        rig_sha = canonical_sha256(rig)
        report = run_setup_probes(
            rig,
            bundle.manifest,
            resolved,
            rig_sha256=rig_sha,
            bundle_path=bundle.path,
        )
        if report["status"] == "rejected":
            raise RigBundleError(_probe_error(report))
        destination, published_sha = RigBundleStore(state_root).publish(
            project_id, rig, run_manifest, report, bundle.path
        )
    except (
        LayerManifestBundleError,
        ProjectNotFoundError,
        ProjectStateError,
        RegionRigError,
        RigBundleError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        _print({"ok": False, "error": str(exc)})
        return 2
    _print(
        {
            "ok": True,
            "project_id": project_id,
            "revision": resolved["revision"],
            "layer_manifest_sha256": bundle.sha256,
            "resolved_project_sha256": resolved["sha256"],
            "run_manifest_sha256": canonical_sha256(run_manifest),
            "rig_sha256": published_sha,
            "probe_report_sha256": canonical_sha256(report),
            "probe_status": report["status"],
            "bundle_sha256": destination.name,
            "bundle_path": str(destination),
        }
    )
    return 0


def run_rig_probes_command(
    project_id: str,
    rig_path: Path,
    workspace: Path,
    state_root: Path,
    *,
    layer_manifest_sha256: str,
) -> int:
    try:
        project = _project_store(workspace, state_root).get_project(project_id)
        resolved = _resolved(project)
        bundle = LayerManifestBundleReader(state_root).load(
            project_id, layer_manifest_sha256
        )
        rig = read_json(Path(rig_path))
        report = run_setup_probes(
            rig,
            bundle.manifest,
            resolved,
            rig_sha256=canonical_sha256(rig),
            bundle_path=bundle.path,
        )
    except (
        LayerManifestBundleError,
        ProjectNotFoundError,
        ProjectStateError,
        RigBundleError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        _print({"ok": False, "error": str(exc)})
        return 2
    _print(report)
    return {"passed": 0, "manual_required": 1, "rejected": 2}[report["status"]]


def _project_arguments(
    parser: argparse.ArgumentParser, default_workspace: Path, default_state_root: Path
) -> None:
    parser.add_argument("project_id", help="Audit project identifier")
    parser.add_argument(
        "--layer-manifest-sha256",
        required=True,
        help="Exact immutable Layer Manifest bundle SHA-256",
    )
    parser.add_argument("--workspace", type=Path, default=default_workspace)
    parser.add_argument("--state-root", type=Path, default=default_state_root)


def _resolved(project: dict[str, Any]) -> dict[str, Any]:
    resolved = project.get("resolved")
    if not isinstance(resolved, dict):
        raise ProjectStateError("Project has no resolved snapshot")
    return resolved


def _project_store(workspace: Path, state_root: Path) -> ProjectStore:
    return ProjectStore(
        workspace, state_root=state_root, measure_composite_quality=False
    )


def _probe_error(report: dict[str, Any]) -> str:
    messages = [
        str(check.get("message"))
        for check in report.get("checks", [])
        if check.get("status") == "rejected" and check.get("message")
    ]
    return "Setup probes rejected the RigIR" + (f": {'; '.join(messages)}" if messages else "")


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
