"""CLI registration and bounded output for P10.3a preview compilation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .p10_preview_commands import (
    P10PreviewCommandError,
    compile_body_sway_preview_command,
)


COMMAND = "compile-body-sway-preview"


def add_p10_preview_subcommands(
    subparsers: Any, default_state_root: Path,
) -> None:
    """Register the exact-chain, zero-write preview package compiler."""

    parser = subparsers.add_parser(
        COMMAND,
        help="Compile a temporary Spine 4.2 body-sway preview in memory",
    )
    parser.add_argument("project_id", metavar="PROJECT")
    for option in _EXACT_OPTIONS:
        parser.add_argument(option, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--decision", type=Path, required=True)
    parser.add_argument("--probe-report", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, default=default_state_root)
    parser.add_argument(
        "--document-only", action="store_true",
        help="Print only canonical TemporaryBodySwayPreview v1 metadata",
    )


def dispatch_p10_preview_command(args: argparse.Namespace) -> int | None:
    """Dispatch the preview compiler or ignore another command namespace."""

    if getattr(args, "command", None) != COMMAND:
        return None
    try:
        result = compile_body_sway_preview_command(
            args.state_root,
            args.project_id,
            args.candidates,
            args.decision,
            args.probe_report,
            layer_manifest_sha256=args.layer_manifest_sha256,
            p3_rig_sha256=args.p3_rig_sha256,
            p3_bundle_sha256=args.p3_bundle_sha256,
            motion_instance_sha256=args.motion_instance_sha256,
            motion_retarget_bundle_sha256=
                args.motion_retarget_bundle_sha256,
            motion_instance_v2_sha256=args.motion_instance_v2_sha256,
            reviewed_motion_bundle_sha256=
                args.reviewed_motion_bundle_sha256,
        )
    except P10PreviewCommandError as exc:
        _print({"error": str(exc), "ok": False, "status": "error"})
        return 2
    if args.document_only:
        _print(result.document)
        return 0
    _print({
        "ok": True,
        "status": "ready_for_official_runtime_capture",
        "input_paths": [str(path) for path in result.input_paths],
        "idle_behavior_candidates_sha256":
            result.idle_behavior_candidates_sha256,
        "idle_behavior_decision_sha256":
            result.idle_behavior_decision_sha256,
        "body_sway_probe_report_sha256":
            result.body_sway_probe_report_sha256,
        "temporary_preview_sha256": result.temporary_preview_sha256,
        "artifact_set_sha256": result.artifact_set_sha256,
        "artifact_files": result.artifact_files,
        "manifest": result.document,
    })
    return 0


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))


_EXACT_OPTIONS = (
    "--layer-manifest-sha256",
    "--p3-rig-sha256",
    "--p3-bundle-sha256",
    "--motion-instance-sha256",
    "--motion-retarget-bundle-sha256",
    "--motion-instance-v2-sha256",
    "--reviewed-motion-bundle-sha256",
)
