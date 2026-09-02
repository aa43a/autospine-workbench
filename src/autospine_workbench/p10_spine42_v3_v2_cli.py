"""Version-isolated CLI for P10.7a v2 Spine 4.2 bundles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .p10_capture_job_store import P10CaptureJobStore
from .p10_spine42_v3_commands_v2 import (
    P10Spine42V3CommandV2Error,
    compile_body_sway_spine42_v3_v2_command,
    verify_body_sway_spine42_v3_v2_command,
)
from .project_store import ProjectStore, ProjectStoreError


COMPILE_COMMAND = "compile-body-sway-spine42-v3-v2"
VERIFY_COMMAND = "verify-body-sway-spine42-v3-v2"
COMPILE_ERROR_CODE = "body_sway_spine42_v3_v2_compile_failed"
VERIFY_ERROR_CODE = "body_sway_spine42_v3_v2_verify_failed"
COMPILE_ERROR_MESSAGE = "Body-sway Spine 4.2 v3 v2 compilation failed."
VERIFY_ERROR_MESSAGE = "Body-sway Spine 4.2 v3 v2 verification failed."


class _ReadOnlyCaptureJobs:
    def __init__(self, state_root: Path) -> None:
        self._store = P10CaptureJobStore(state_root)

    def get(self, job_id: str) -> dict[str, Any]:
        return self._store.load(job_id).public_document()


def add_p10_spine42_v3_v2_subcommands(
    subparsers: Any,
    default_state_root: Path,
) -> None:
    """Register exact v2-source compile and historical verify commands."""

    compile_parser = subparsers.add_parser(
        COMPILE_COMMAND,
        help="Compile one exact P10.6b v2 MotionInstance into Spine 4.2",
    )
    compile_parser.add_argument("project_id", metavar="PROJECT")
    compile_parser.add_argument("--motion-instance-v3-sha256", required=True)
    compile_parser.add_argument(
        "--motion-instance-v3-bundle-sha256", required=True,
    )
    compile_parser.add_argument(
        "--workspace", type=Path,
        default=Path(default_state_root).parent.parent,
    )
    _state_root(compile_parser, default_state_root)

    verify_parser = subparsers.add_parser(
        VERIFY_COMMAND,
        help="Verify one exact historical P10.7a v2 Spine 4.2 bundle",
    )
    verify_parser.add_argument("project_id", metavar="PROJECT")
    verify_parser.add_argument("--skeleton-json-sha256", required=True)
    verify_parser.add_argument("--bundle-sha256", required=True)
    _state_root(verify_parser, default_state_root)


def dispatch_p10_spine42_v3_v2_command(
    args: argparse.Namespace,
) -> int | None:
    """Dispatch with canonical success and fixed path-free failures."""

    command = getattr(args, "command", None)
    if command not in {COMPILE_COMMAND, VERIFY_COMMAND}:
        return None
    try:
        if command == COMPILE_COMMAND:
            store = ProjectStore(
                args.workspace, state_root=args.state_root,
                measure_composite_quality=False,
            )
            result = compile_body_sway_spine42_v3_v2_command(
                _ReadOnlyCaptureJobs(store.state_root), store,
                args.project_id,
                motion_instance_v3_sha256=args.motion_instance_v3_sha256,
                motion_instance_v3_bundle_sha256=(
                    args.motion_instance_v3_bundle_sha256
                ),
            )
        else:
            result = verify_body_sway_spine42_v3_v2_command(
                args.state_root, args.project_id,
                skeleton_json_sha256=args.skeleton_json_sha256,
                bundle_sha256=args.bundle_sha256,
            )
    except _FAILURES:
        compiling = command == COMPILE_COMMAND
        _print({
            "error_code": (
                COMPILE_ERROR_CODE if compiling else VERIFY_ERROR_CODE
            ),
            "message": (
                COMPILE_ERROR_MESSAGE if compiling else VERIFY_ERROR_MESSAGE
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
    OSError, P10Spine42V3CommandV2Error, ProjectStoreError,
    RuntimeError, TypeError, UnicodeError, ValueError,
)


__all__ = [
    "COMPILE_COMMAND", "VERIFY_COMMAND",
    "add_p10_spine42_v3_v2_subcommands",
    "dispatch_p10_spine42_v3_v2_command",
]
