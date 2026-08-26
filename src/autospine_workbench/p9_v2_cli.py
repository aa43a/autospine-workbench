"""CLI registration and canonical dispatch for read-only P9.5 outputs."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from .p9_v2_commands import (
    P9V2CommandError,
    compile_motion_instance_v2_command,
    export_spine42_v2_command,
)


def add_p9_v2_subcommands(subparsers: Any, state_root: Path) -> None:
    """Register exact-address MotionInstance and Spine v2 commands."""

    compile_parser = subparsers.add_parser(
        "compile-motion-instance-v2",
        help="Compile reviewed P9 policy over one exact P5 instance",
    )
    _p5_arguments(compile_parser)
    _document_only(compile_parser)
    _state_root(compile_parser, state_root)

    export_parser = subparsers.add_parser(
        "export-spine42-v2",
        help="Build a read-only Spine 4.2 v2 export report",
    )
    _p5_arguments(export_parser)
    export_parser.add_argument("--p3-rig-sha256", required=True)
    export_parser.add_argument("--p3-bundle-sha256", required=True)
    _document_only(export_parser)
    _state_root(export_parser, state_root)


def dispatch_p9_v2_command(args: argparse.Namespace) -> int | None:
    """Dispatch a P9.5 command, or ignore an unrelated namespace."""

    command = getattr(args, "command", None)
    try:
        if command == "compile-motion-instance-v2":
            result = compile_motion_instance_v2_command(
                args.state_root,
                args.project_id,
                args.reviewed_policy,
                motion_instance_sha256=args.motion_instance_sha256,
                motion_retarget_bundle_sha256=(
                    args.motion_retarget_bundle_sha256
                ),
            )
        elif command == "export-spine42-v2":
            result = export_spine42_v2_command(
                args.state_root,
                args.project_id,
                args.reviewed_policy,
                p3_rig_sha256=args.p3_rig_sha256,
                p3_bundle_sha256=args.p3_bundle_sha256,
                motion_instance_sha256=args.motion_instance_sha256,
                motion_retarget_bundle_sha256=(
                    args.motion_retarget_bundle_sha256
                ),
            )
        else:
            return None
    except P9V2CommandError as exc:
        _print({"error": str(exc), "ok": False, "status": "error"})
        return 2
    if args.document_only:
        _print(result.report)
        return 0
    payload = _jsonable(asdict(result))
    payload.update(ok=True, status="passed")
    _print(payload)
    return 0


def _p5_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("project_id", metavar="PROJECT")
    parser.add_argument("--motion-instance-sha256", required=True)
    parser.add_argument("--motion-retarget-bundle-sha256", required=True)
    parser.add_argument("--reviewed-policy", type=Path, required=True)


def _state_root(parser: argparse.ArgumentParser, default: Path) -> None:
    parser.add_argument("--state-root", type=Path, default=default)


def _document_only(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--document-only",
        action="store_true",
        help="Print only the canonical compiled document/report",
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
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ))
