"""Canonical CLI adapter for the zero-write P10.5d seam probe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .p10_dynamic_seam_commands import (
    P10DynamicSeamCommandError,
    compile_body_sway_dynamic_seam_probe_command,
)


COMMAND = "compile-body-sway-dynamic-seam-probe"
ERROR_CODE = "body_sway_dynamic_seam_probe_failed"
ERROR_MESSAGE = "Body-sway dynamic seam probe compilation failed."


def add_p10_dynamic_seam_subcommands(
    subparsers: Any,
    default_state_root: Path,
) -> None:
    """Register the exact-address, zero-write P10.5d command."""

    parser = subparsers.add_parser(
        COMMAND,
        help="Prove reviewed seam-anchor proximity over body-sway motion",
    )
    parser.add_argument("project_id", metavar="PROJECT")
    parser.add_argument(
        "--continuous-proof",
        required=True,
        type=Path,
        help="Exact canonical P10.4b2 continuous proof JSON",
    )
    parser.add_argument("--reviewed-set-sha256", required=True)
    parser.add_argument("--reviewed-set-bundle-sha256", required=True)
    parser.add_argument(
        "--state-root",
        type=Path,
        default=Path(default_state_root),
    )


def dispatch_p10_dynamic_seam_command(
    args: argparse.Namespace,
) -> int | None:
    """Dispatch P10.5d with fixed, redacted failures and canonical output."""

    if getattr(args, "command", None) != COMMAND:
        return None
    try:
        result = compile_body_sway_dynamic_seam_probe_command(
            args.state_root,
            args.project_id,
            args.continuous_proof,
            reviewed_set_sha256=args.reviewed_set_sha256,
            reviewed_set_bundle_sha256=(
                args.reviewed_set_bundle_sha256
            ),
        )
    except P10DynamicSeamCommandError:
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
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ))
