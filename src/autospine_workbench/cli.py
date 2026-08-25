"""Command-line entry point for the AutoSpine workbench."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .manifest_commands import materialize_manifest_command as _materialize_manifest
from .pose_commands import analyze_joints as _analyze_joints
from .pose_commands import evaluate_pose_command as _evaluate_pose
from .pose_commands import import_pose as _import_pose
from .rig_validation import RigSemanticValidator
from .rig_commands import (
    add_rig_subcommands,
    compile_rig_command as _compile_rig,
    run_rig_probes_command as _run_rig_probes,
    verify_setup_golden_command as _verify_setup_golden,
)
from .server import create_server
from .split_preview_commands import (
    add_split_preview_subcommand,
    publish_split_previews_command as _publish_split_previews,
)


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
    analyze.add_argument(
        "--provider",
        choices=("audit-bbox", "pose-alpha", "pose-geometry"),
        default="audit-bbox",
        help=(
            "Candidate provider: audit-bbox, pose-alpha, or geometry-bound "
            "pose-geometry (default: audit-bbox)"
        ),
    )
    analyze.add_argument(
        "--pose-observations",
        type=Path,
        help="Canonical pose-observations v1/v2 JSON; required by pose providers",
    )
    analyze.add_argument(
        "--alpha-threshold",
        type=int,
        default=8,
        help="Minimum alpha byte used as geometry evidence (default: 8)",
    )
    import_pose = subparsers.add_parser(
        "import-pose",
        help="Adapt pinned COCO17 detections to canonical pose observations v2",
    )
    import_pose.add_argument("project_id", help="Audit project identifier")
    import_pose.add_argument("detections", type=Path, help="Pinned COCO17 detections v1 JSON")
    import_pose.add_argument(
        "--workspace",
        type=Path,
        default=_project_root().parent,
        help="Workspace containing tmp/psd_audit/results",
    )
    import_pose.add_argument(
        "--state-root",
        type=Path,
        default=_project_root() / "workspace",
        help="Root for content-addressed analysis artifacts",
    )
    import_pose.add_argument("--selected-index", type=int, help="Required when multiple people exist")
    import_pose.add_argument(
        "--selection-method",
        choices=("manual", "largest_area"),
        help="Required when multiple people exist",
    )
    import_pose.add_argument(
        "--side-mapping",
        required=True,
        choices=("as_reported", "swap_left_right"),
        help="Map COCO anatomical sides to character sides without screen-x inference",
    )
    import_pose.add_argument(
        "--view-orientation",
        required=True,
        choices=("front", "back", "left_profile", "right_profile", "three_quarter", "unknown"),
        help="Explicit source-view declaration; does not infer side mapping",
    )
    import_pose.add_argument(
        "--mirror-state",
        required=True,
        choices=("not_mirrored", "mirrored", "unknown"),
        help="Explicit project-composite mirror declaration",
    )
    evaluate_pose = subparsers.add_parser(
        "evaluate-pose",
        help="Compare canonical pose observations with manually reviewed limb joints",
    )
    evaluate_pose.add_argument("project_id", help="Audit project identifier")
    evaluate_pose.add_argument(
        "pose_observations", type=Path, help="Canonical pose-observations v1 or v2 JSON"
    )
    evaluate_pose.add_argument(
        "--workspace",
        type=Path,
        default=_project_root().parent,
        help="Workspace containing tmp/psd_audit/results",
    )
    evaluate_pose.add_argument(
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
    add_split_preview_subcommand(
        subparsers,
        default_workspace=_project_root().parent,
        default_state_root=_project_root() / "workspace",
    )
    add_rig_subcommands(
        subparsers,
        default_workspace=_project_root().parent,
        default_state_root=_project_root() / "workspace",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate-rig":
        return _validate_rig(args.rig)
    if args.command == "analyze-joints":
        return _analyze_joints(
            args.project_id,
            args.workspace,
            args.state_root,
            provider_name=args.provider,
            pose_path=args.pose_observations,
            alpha_threshold=args.alpha_threshold,
        )
    if args.command == "import-pose":
        return _import_pose(
            args.project_id,
            args.detections,
            args.workspace,
            args.state_root,
            selected_index=args.selected_index,
            selection_method=args.selection_method,
            side_mapping=args.side_mapping,
            view_orientation=args.view_orientation,
            mirror_state=args.mirror_state,
        )
    if args.command == "evaluate-pose":
        return _evaluate_pose(
            args.project_id,
            args.pose_observations,
            args.workspace,
            args.state_root,
        )
    if args.command == "materialize-manifest":
        return _materialize_manifest(args.project_id, args.workspace, args.state_root)
    if args.command == "publish-split-previews":
        return _publish_split_previews(
            args.project_id, args.workspace, args.state_root
        )
    if args.command == "compile-rig":
        return _compile_rig(
            args.project_id,
            args.workspace,
            args.state_root,
            layer_manifest_sha256=args.layer_manifest_sha256,
            allow_manual_required=args.allow_manual_required,
        )
    if args.command == "run-probes":
        return _run_rig_probes(
            args.project_id,
            args.rig,
            args.workspace,
            args.state_root,
            layer_manifest_sha256=args.layer_manifest_sha256,
        )
    if args.command == "verify-setup-golden":
        return _verify_setup_golden(args.bundle, args.golden_contract)
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
