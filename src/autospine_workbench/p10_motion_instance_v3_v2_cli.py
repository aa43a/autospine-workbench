"""Automatic exact-address CLI for the P10.6b v2 source chain."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .p10_capture_job_store import P10CaptureJobStore
from .p10_motion_instance_v3_commands_v2 import (
    P10MotionInstanceV3CommandV2Error,
    compile_body_sway_motion_instance_v3_v2_command,
    verify_body_sway_motion_instance_v3_v2_command,
)
from .project_store import ProjectStore, ProjectStoreError


COMPILE_COMMAND = "compile-body-sway-motion-instance-v3-v2"
VERIFY_COMMAND = "verify-body-sway-motion-instance-v3-v2"
COMPILE_ERROR_CODE = "body_sway_motion_instance_v3_v2_compile_failed"
VERIFY_ERROR_CODE = "body_sway_motion_instance_v3_v2_verify_failed"
COMPILE_ERROR_MESSAGE = "Body-sway MotionInstance v3 v2 compilation failed."
VERIFY_ERROR_MESSAGE = "Body-sway MotionInstance v3 v2 verification failed."


class _ReadOnlyCaptureJobs:
    def __init__(self, state_root: Path) -> None:
        self._store = P10CaptureJobStore(state_root)

    def get(self, job_id: str) -> dict[str, Any]:
        return self._store.load(job_id).public_document()


def add_p10_motion_instance_v3_v2_subcommands(
    subparsers: Any,
    default_state_root: Path,
) -> None:
    """Register v2-source compile and exact historical verification."""

    compile_parser = subparsers.add_parser(
        COMPILE_COMMAND,
        help="Compile MotionInstance v3 from one exact P10.5d v2 bundle",
    )
    compile_parser.add_argument("project_id", metavar="PROJECT")
    compile_parser.add_argument(
        "--dynamic-seam-probe-sha256", required=True,
    )
    compile_parser.add_argument(
        "--dynamic-seam-bundle-sha256", required=True,
    )
    compile_parser.add_argument(
        "--workspace", type=Path,
        default=Path(default_state_root).parent.parent,
    )
    _state_root(compile_parser, default_state_root)

    verify_parser = subparsers.add_parser(
        VERIFY_COMMAND,
        help="Verify one exact historical v2-source MotionInstance v3 bundle",
    )
    verify_parser.add_argument("project_id", metavar="PROJECT")
    verify_parser.add_argument("--motion-instance-v3-sha256", required=True)
    verify_parser.add_argument("--bundle-sha256", required=True)
    _state_root(verify_parser, default_state_root)


def dispatch_p10_motion_instance_v3_v2_command(
    args: argparse.Namespace,
) -> int | None:
    """Dispatch with canonical success output and fixed path-free failures."""

    command = getattr(args, "command", None)
    if command not in {COMPILE_COMMAND, VERIFY_COMMAND}:
        return None
    try:
        if command == COMPILE_COMMAND:
            store = ProjectStore(args.workspace, state_root=args.state_root)
            result = compile_body_sway_motion_instance_v3_v2_command(
                _ReadOnlyCaptureJobs(store.state_root), store,
                args.project_id,
                dynamic_seam_probe_sha256=(
                    args.dynamic_seam_probe_sha256
                ),
                dynamic_seam_bundle_sha256=(
                    args.dynamic_seam_bundle_sha256
                ),
            )
        else:
            result = verify_body_sway_motion_instance_v3_v2_command(
                args.state_root, args.project_id,
                motion_instance_v3_sha256=args.motion_instance_v3_sha256,
                bundle_sha256=args.bundle_sha256,
            )
    except _FAILURES:
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


_FAILURES = (
    OSError, P10MotionInstanceV3CommandV2Error, ProjectStoreError,
    RuntimeError, TypeError, UnicodeError, ValueError,
)


__all__ = [
    "COMPILE_COMMAND", "VERIFY_COMMAND",
    "add_p10_motion_instance_v3_v2_subcommands",
    "dispatch_p10_motion_instance_v3_v2_command",
]
