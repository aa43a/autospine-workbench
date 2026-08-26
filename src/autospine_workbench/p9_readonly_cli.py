"""Argument registration and dispatch for read-only P9 commands."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from .p9_readonly_commands import (
    P9ReadOnlyCommandError,
    compile_heading_evidence_command,
    compile_kimodo_policy_evidence_command,
    probe_depth_order_command,
    probe_foot_lock_command,
)


def add_p9_readonly_subcommands(subparsers: Any, state_root: Path) -> None:
    """Register P9.0-P9.3 commands with explicit content addresses."""

    policy = subparsers.add_parser(
        "compile-kimodo-policy-evidence",
        help="Compile candidate-free Kimodo policy evidence from exact P7/P8",
    )
    _p7_p8_arguments(policy)
    _document_only(policy)
    _state_root(policy, state_root)

    heading = subparsers.add_parser(
        "compile-heading-evidence",
        help="Compile reviewed heading evidence from exact P7/P8",
    )
    heading.add_argument("--policy-map", type=Path, required=True)
    _p7_p8_arguments(heading)
    _document_only(heading)
    _state_root(heading, state_root)

    foot = subparsers.add_parser(
        "probe-foot-lock",
        help="Report review-only foot-lock candidates from exact P8/P5",
    )
    foot.add_argument("project_id", metavar="PROJECT")
    _p8_p5_arguments(foot)
    foot.add_argument(
        "--max-correction-reference-ratio", type=float, required=True
    )
    foot.add_argument("--max-residual-px", type=float, required=True)
    _document_only(foot)
    _state_root(foot, state_root)

    depth = subparsers.add_parser(
        "probe-depth-order",
        help="Report reviewed pairwise depth candidates from exact P8/P5/P3",
    )
    depth.add_argument("project_id", metavar="PROJECT")
    depth.add_argument("--policy", type=Path, required=True)
    _p8_p5_arguments(depth)
    depth.add_argument("--p3-rig-sha256", required=True)
    depth.add_argument("--p3-bundle-sha256", required=True)
    _document_only(depth)
    _state_root(depth, state_root)


def dispatch_p9_readonly_command(args: argparse.Namespace) -> int | None:
    """Dispatch a P9 read-only command, or ignore unrelated namespaces."""

    command = getattr(args, "command", None)
    try:
        if command == "compile-kimodo-policy-evidence":
            result = compile_kimodo_policy_evidence_command(
                args.state_root,
                motion_sha256=args.motion_sha256,
                motion_bundle_sha256=args.motion_bundle_sha256,
                projected_motion_sha256=args.projected_motion_sha256,
                projected_bundle_sha256=args.projected_bundle_sha256,
            )
        elif command == "compile-heading-evidence":
            result = compile_heading_evidence_command(
                args.state_root,
                args.policy_map,
                motion_sha256=args.motion_sha256,
                motion_bundle_sha256=args.motion_bundle_sha256,
                projected_motion_sha256=args.projected_motion_sha256,
                projected_bundle_sha256=args.projected_bundle_sha256,
            )
        elif command == "probe-foot-lock":
            result = probe_foot_lock_command(
                args.state_root,
                args.project_id,
                projected_motion_sha256=args.projected_motion_sha256,
                projected_bundle_sha256=args.projected_bundle_sha256,
                motion_instance_sha256=args.motion_instance_sha256,
                motion_retarget_bundle_sha256=(
                    args.motion_retarget_bundle_sha256
                ),
                max_correction_reference_ratio=(
                    args.max_correction_reference_ratio
                ),
                max_residual_px=args.max_residual_px,
            )
        elif command == "probe-depth-order":
            result = probe_depth_order_command(
                args.state_root,
                args.project_id,
                args.policy,
                projected_motion_sha256=args.projected_motion_sha256,
                projected_bundle_sha256=args.projected_bundle_sha256,
                motion_instance_sha256=args.motion_instance_sha256,
                motion_retarget_bundle_sha256=(
                    args.motion_retarget_bundle_sha256
                ),
                p3_rig_sha256=args.p3_rig_sha256,
                p3_bundle_sha256=args.p3_bundle_sha256,
            )
        else:
            return None
    except P9ReadOnlyCommandError as exc:
        _print({"error": str(exc), "ok": False, "status": "error"})
        return 2
    if args.document_only:
        _print(result.report)
        return 0
    payload = _jsonable(asdict(result))
    payload.update(ok=True, status="passed")
    _print(payload)
    return 0


def _p7_p8_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--motion-sha256", required=True)
    parser.add_argument("--motion-bundle-sha256", required=True)
    parser.add_argument("--projected-motion-sha256", required=True)
    parser.add_argument("--projected-bundle-sha256", required=True)


def _p8_p5_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--projected-motion-sha256", required=True)
    parser.add_argument("--projected-bundle-sha256", required=True)
    parser.add_argument("--motion-instance-sha256", required=True)
    parser.add_argument("--motion-retarget-bundle-sha256", required=True)


def _state_root(parser: argparse.ArgumentParser, default: Path) -> None:
    parser.add_argument("--state-root", type=Path, default=default)


def _document_only(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--document-only", action="store_true",
        help="Print only the canonical report document for pipeline handoff",
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))
