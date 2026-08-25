"""Argument and dispatch layer for exact-address P5 motion services."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from .motion_bvh_commands import (
    BvhMotionCommandError,
    compile_bvh_motion_bundle,
    verify_bvh_motion_bundle,
)
from .motion_retarget_commands import (
    MotionRetargetCommandError,
    compile_motion_retarget_bundle,
    verify_motion_retarget_bundle,
)


def add_motion_stage_subcommands(
    subparsers: Any, default_state_root: Path,
) -> None:
    """Register P5 BVH and retarget commands on an existing parser."""

    compile_bvh = subparsers.add_parser(
        "compile-bvh-motion",
        help="Compile one explicit BVH source and map into a verified bundle",
    )
    compile_bvh.add_argument("source", metavar="SOURCE", type=Path)
    compile_bvh.add_argument("map", metavar="MAP", type=Path)
    _add_state_root(compile_bvh, default_state_root)

    verify_bvh = subparsers.add_parser(
        "verify-bvh-motion",
        help="Verify one exact BVH MotionIR bundle address",
    )
    verify_bvh.add_argument("--clip-sha256", required=True)
    verify_bvh.add_argument("--bundle-sha256", required=True)
    _add_state_root(verify_bvh, default_state_root)

    compile_retarget = subparsers.add_parser(
        "compile-motion-retarget",
        help="Retarget one exact P3/P4/MotionIR identity chain",
    )
    compile_retarget.add_argument("project_id", metavar="PROJECT")
    for option in _RETARGET_INPUT_OPTIONS:
        compile_retarget.add_argument(option, required=True)
    _add_state_root(compile_retarget, default_state_root)

    verify_retarget = subparsers.add_parser(
        "verify-motion-retarget",
        help="Verify one exact immutable motion-retarget bundle address",
    )
    verify_retarget.add_argument("project_id", metavar="PROJECT")
    verify_retarget.add_argument("--instance-sha256", required=True)
    verify_retarget.add_argument("--bundle-sha256", required=True)
    _add_state_root(verify_retarget, default_state_root)


def dispatch_motion_stage_command(args: argparse.Namespace) -> int | None:
    """Dispatch a P5 namespace, returning ``None`` for unrelated commands."""

    command = getattr(args, "command", None)
    if command == "compile-bvh-motion":
        return _run(
            compile_bvh_motion_bundle,
            _bvh_payload,
            args.state_root,
            args.source,
            args.map,
        )
    if command == "verify-bvh-motion":
        return _run(
            verify_bvh_motion_bundle,
            _bvh_payload,
            args.state_root,
            args.clip_sha256,
            args.bundle_sha256,
        )
    if command == "compile-motion-retarget":
        return _run(
            compile_motion_retarget_bundle,
            _retarget_payload,
            args.state_root,
            args.project_id,
            p3_rig_sha256=args.p3_rig_sha256,
            p3_bundle_sha256=args.p3_bundle_sha256,
            p4_profile_sha256=args.p4_profile_sha256,
            p4_bundle_sha256=args.p4_bundle_sha256,
            motion_clip_sha256=args.motion_clip_sha256,
            motion_bundle_sha256=args.motion_bundle_sha256,
        )
    if command == "verify-motion-retarget":
        return _run(
            verify_motion_retarget_bundle,
            _retarget_payload,
            args.state_root,
            args.project_id,
            instance_sha256=args.instance_sha256,
            bundle_sha256=args.bundle_sha256,
        )
    return None


def _run(
    service: Callable[..., Any],
    serializer: Callable[[Any], dict[str, Any]],
    *positional: Any,
    **keywords: Any,
) -> int:
    try:
        result = service(*positional, **keywords)
        response = serializer(result)
        response.update(ok=True, status="passed")
    except _SERVICE_ERRORS as exc:
        _print({"ok": False, "status": "error", "error": str(exc)})
        return 2
    _print(response)
    return 0


def _bvh_payload(result: Any) -> dict[str, Any]:
    return {
        "path": str(result.path),
        "clip_id": result.clip_id,
        "map_id": result.map_id,
        "raw_bvh_sha256": result.raw_bvh_sha256,
        "raw_bvh_byte_length": result.raw_bvh_byte_length,
        "bvh_map_sha256": result.bvh_map_sha256,
        "motion_ir_sha256": result.motion_ir_sha256,
        "clip_sha256": result.clip_sha256,
        "run_sha256": result.run_sha256,
        "bundle_sha256": result.bundle_sha256,
        "source_kind": result.source_kind,
        "reused": result.reused,
    }


def _retarget_payload(result: Any) -> dict[str, Any]:
    return {
        "path": str(result.path),
        "project_id": result.project_id,
        "clip_id": result.clip_id,
        "source_addresses": dict(result.source_addresses),
        "target_profile_sha256": result.target_profile_sha256,
        "instance_sha256": result.instance_sha256,
        "retarget_run_identity_sha256": result.retarget_run_identity_sha256,
        "run_sha256": result.run_sha256,
        "report_sha256": result.report_sha256,
        "mesh_regression_sha256": result.mesh_regression_sha256,
        "bundle_sha256": result.bundle_sha256,
        "summary": result.summary,
        "reused": result.reused,
    }


def _add_state_root(parser: argparse.ArgumentParser, default: Path) -> None:
    parser.add_argument("--state-root", type=Path, default=Path(default))


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(
        value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True,
    ))


_RETARGET_INPUT_OPTIONS = (
    "--p3-rig-sha256",
    "--p3-bundle-sha256",
    "--p4-profile-sha256",
    "--p4-bundle-sha256",
    "--motion-clip-sha256",
    "--motion-bundle-sha256",
)

_SERVICE_ERRORS = (BvhMotionCommandError, MotionRetargetCommandError)
