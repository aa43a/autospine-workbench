"""Command-line entry point for the AutoSpine workbench."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .artifact_store import ArtifactStoreError, ImmutableJsonArtifactStore
from .joint_candidates import AuditBBoxHeuristicProvider
from .layer_manifest import (
    LayerManifestBuilder,
    LayerManifestBundleStore,
    LayerManifestError,
)
from .project_store import ProjectStore, ProjectStoreError
from .rig_validation import RigSemanticValidator
from .server import create_server


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m autospine_workbench")
    subparsers = parser.add_subparsers(dest="command", required=True)
    serve = subparsers.add_parser("serve", help="Run the local workbench HTTP API")
    serve.add_argument("--host", default="127.0.0.1", help="Loopback host (default: 127.0.0.1)")
    serve.add_argument("--port", default=8765, type=int, help="TCP port (default: 8765)")
    serve.add_argument(
        "--workspace",
        type=Path,
        default=_project_root().parent,
        help="Workspace containing tmp/psd_audit/results",
    )
    serve.add_argument(
        "--state-root",
        type=Path,
        default=_project_root() / "workspace",
        help="Directory for atomic override state",
    )
    serve.add_argument(
        "--web-root",
        type=Path,
        default=None,
        help="Optional built frontend directory to serve",
    )
    validate_rig = subparsers.add_parser(
        "validate-rig",
        help="Validate RigIR cross-references, topology, and numeric invariants",
    )
    validate_rig.add_argument("rig", type=Path, help="Path to a RigIR JSON document")
    analyze = subparsers.add_parser(
        "analyze-joints",
        help="Publish a pinned joint-candidate analysis artifact",
    )
    analyze.add_argument("project_id", help="Audit project identifier")
    analyze.add_argument(
        "--workspace",
        type=Path,
        default=_project_root().parent,
        help="Workspace containing tmp/psd_audit/results",
    )
    analyze.add_argument(
        "--state-root",
        type=Path,
        default=_project_root() / "workspace",
        help="Root for content-addressed analysis artifacts",
    )
    materialize = subparsers.add_parser(
        "materialize-manifest",
        help="Publish a region-first Layer Manifest bundle from reviewed state",
    )
    materialize.add_argument("project_id", help="Audit project identifier")
    materialize.add_argument(
        "--workspace",
        type=Path,
        default=_project_root().parent,
        help="Workspace containing tmp/psd_audit/results",
    )
    materialize.add_argument(
        "--state-root",
        type=Path,
        default=_project_root() / "workspace",
        help="Root for immutable build bundles",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate-rig":
        return _validate_rig(args.rig)
    if args.command == "analyze-joints":
        return _analyze_joints(args.project_id, args.workspace, args.state_root)
    if args.command == "materialize-manifest":
        return _materialize_manifest(args.project_id, args.workspace, args.state_root)
    if args.command != "serve":
        raise AssertionError(f"Unhandled command: {args.command}")
    try:
        server = create_server(
            args.host,
            args.port,
            args.workspace,
            web_root=args.web_root,
            state_root=args.state_root,
        )
    except (OSError, ValueError) as exc:
        build_parser().error(str(exc))
    bound_host, bound_port = server.server_address[:2]
    print(f"AutoSpine workbench serving on http://{bound_host}:{bound_port}")
    print(f"Workspace: {Path(args.workspace).expanduser().resolve()}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nStopping AutoSpine workbench.")
    finally:
        server.server_close()
    return 0


def _validate_rig(path: Path) -> int:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"valid": False, "issues": [{"code": "invalid_document", "path": "", "message": str(exc), "severity": "error"}]}))
        return 2
    issues = RigSemanticValidator().validate(document)
    valid = not any(issue.severity == "error" for issue in issues)
    print(
        json.dumps(
            {"valid": valid, "issues": [issue.to_dict() for issue in issues]},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if valid else 1


def _analyze_joints(project_id: str, workspace: Path, state_root: Path) -> int:
    try:
        project = ProjectStore(workspace, state_root=state_root).get_project(project_id)
        document = AuditBBoxHeuristicProvider().analyze(project)
        published = ImmutableJsonArtifactStore(state_root).publish(
            "joint-candidates", project_id, document
        )
    except (ProjectStoreError, ArtifactStoreError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(
        json.dumps(
            {
                "ok": True,
                "project_id": project_id,
                "provider": document["analysis"]["provider"],
                "analysis_run_sha256": document["analysis"]["run_sha256"],
                "artifact_sha256": published.sha256,
                "artifact_path": str(published.path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _materialize_manifest(project_id: str, workspace: Path, state_root: Path) -> int:
    try:
        store = ProjectStore(workspace, state_root=state_root)
        project = store.get_project(project_id)
        assets = {
            layer["id"]: store.resolve_asset(project_id, "layer", layer["id"])
            for layer in project["layers"]
        }
        manifest = LayerManifestBuilder().build(project, assets)
        bundle, digest = LayerManifestBundleStore(state_root).publish(
            project_id, manifest, assets
        )
    except (ProjectStoreError, LayerManifestError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(
        json.dumps(
            {
                "ok": True,
                "project_id": project_id,
                "revision": manifest["revision"],
                "manifest_sha256": digest,
                "bundle_path": str(bundle),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0
