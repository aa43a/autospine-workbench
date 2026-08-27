"""Canonical CLI adapter for P10.6b MotionInstance v3 bundles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .p10_motion_instance_v3_commands import (
    P10MotionInstanceV3CommandError,
    compile_body_sway_motion_instance_v3_command,
    verify_body_sway_motion_instance_v3_command,
)


COMPILE_COMMAND = "compile-body-sway-motion-instance-v3"
VERIFY_COMMAND = "verify-body-sway-motion-instance-v3"
COMPILE_ERROR_CODE = "body_sway_motion_instance_v3_compile_failed"
VERIFY_ERROR_CODE = "body_sway_motion_instance_v3_verify_failed"
COMPILE_ERROR_MESSAGE = "Body-sway MotionInstance v3 compilation failed."
VERIFY_ERROR_MESSAGE = "Body-sway MotionInstance v3 verification failed."


def add_p10_motion_instance_v3_subcommands(
    subparsers: Any,
    default_state_root: Path,
) -> None:
    """Register explicit compile and historical verify commands."""

    compile_parser = subparsers.add_parser(
        COMPILE_COMMAND,
        help="Compile and publish one exact body-sway MotionInstance v3",
    )
    compile_parser.add_argument("project_id", metavar="PROJECT")
    compile_parser.add_argument(
        "--admission-wrapper",
        required=True,
        type=Path,
        help="Canonical successful P10.6a CLI JSON wrapper",
    )
    compile_parser.add_argument("--admission-sha256", required=True)
    _state_root(compile_parser, default_state_root)

    verify_parser = subparsers.add_parser(
        VERIFY_COMMAND,
        help="Verify one exact historical MotionInstance v3 bundle",
    )
    verify_parser.add_argument("project_id", metavar="PROJECT")
    verify_parser.add_argument("--motion-instance-v3-sha256", required=True)
    verify_parser.add_argument("--bundle-sha256", required=True)
    _state_root(verify_parser, default_state_root)


def dispatch_p10_motion_instance_v3_command(
    args: argparse.Namespace,
) -> int | None:
    """Dispatch P10.6b with fixed redacted failures and path-free output."""

    command = getattr(args, "command", None)
    if command not in {COMPILE_COMMAND, VERIFY_COMMAND}:
        return None
    try:
        if command == COMPILE_COMMAND:
            result = compile_body_sway_motion_instance_v3_command(
                args.state_root,
                args.project_id,
                args.admission_wrapper,
                admission_sha256=args.admission_sha256,
            )
        else:
            result = verify_body_sway_motion_instance_v3_command(
                args.state_root,
                args.project_id,
                motion_instance_v3_sha256=args.motion_instance_v3_sha256,
                bundle_sha256=args.bundle_sha256,
            )
    except P10MotionInstanceV3CommandError:
        compile_mode = command == COMPILE_COMMAND
        _print({
            "error_code": (
                COMPILE_ERROR_CODE if compile_mode else VERIFY_ERROR_CODE
            ),
            "message": (
                COMPILE_ERROR_MESSAGE if compile_mode
                else VERIFY_ERROR_MESSAGE
            ),
            "ok": False,
            "status": "error",
        })
        return 2
    payload = result.document
    payload.update(ok=True, status=result.mode)
    _print(payload)
    return 0


def _state_root(parser: argparse.ArgumentParser, default: Path) -> None:
    parser.add_argument("--state-root", type=Path, default=Path(default))


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))


__all__ = [
    "COMPILE_COMMAND", "VERIFY_COMMAND",
    "add_p10_motion_instance_v3_subcommands",
    "dispatch_p10_motion_instance_v3_command",
]
