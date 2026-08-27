"""Canonical CLI adapter for zero-write P10.6a consumer admission."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .p10_motion_consumer_admission_commands import (
    P10MotionConsumerAdmissionCommandError,
    compile_body_sway_motion_consumer_admission_command,
)


COMMAND = "compile-body-sway-motion-consumer-admission"
ERROR_CODE = "body_sway_motion_consumer_admission_failed"
ERROR_MESSAGE = "Body-sway motion-consumer admission compilation failed."


def add_p10_motion_consumer_admission_subcommands(
    subparsers: Any,
    default_state_root: Path,
) -> None:
    """Register the exact-address, zero-write P10.6a command."""

    parser = subparsers.add_parser(
        COMMAND,
        help="Admit proved body-sway motion for a version-neutral consumer",
    )
    parser.add_argument("project_id", metavar="PROJECT")
    parser.add_argument(
        "--dynamic-seam-probe",
        required=True,
        type=Path,
        help="Exact canonical P10.5d dynamic seam probe JSON",
    )
    parser.add_argument("--dynamic-seam-probe-sha256", required=True)
    parser.add_argument(
        "--state-root", type=Path, default=Path(default_state_root)
    )


def dispatch_p10_motion_consumer_admission_command(
    args: argparse.Namespace,
) -> int | None:
    """Dispatch P10.6a with fixed, redacted failures and canonical output."""

    if getattr(args, "command", None) != COMMAND:
        return None
    try:
        result = compile_body_sway_motion_consumer_admission_command(
            args.state_root,
            args.project_id,
            args.dynamic_seam_probe,
            dynamic_seam_probe_sha256=args.dynamic_seam_probe_sha256,
        )
    except P10MotionConsumerAdmissionCommandError:
        _print({
            "error_code": ERROR_CODE,
            "message": ERROR_MESSAGE,
            "ok": False,
            "status": "error",
        })
        return 2
    payload = result.document
    payload.update(ok=True, status="compiled")
    _print(payload)
    return 0


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))
