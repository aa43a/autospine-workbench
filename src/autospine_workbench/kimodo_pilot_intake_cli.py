"""CLI adapter for the zero-write real Kimodo pilot intake audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .kimodo_pilot_intake_commands import (
    KimodoPilotIntakeCommandError,
    audit_kimodo_pilot_intake_command,
)


COMMAND = "audit-kimodo-pilot-intake"
ERROR_CODE = "kimodo_pilot_intake_audit_failed"
ERROR_MESSAGE = "Kimodo pilot intake audit failed."


def add_kimodo_pilot_intake_subcommands(subparsers: Any) -> None:
    """Register one explicit six-input, zero-write admission audit."""

    parser = subparsers.add_parser(
        COMMAND,
        help="Audit exact real Kimodo inputs before P7/P8 publication",
    )
    parser.add_argument("raw_npz", metavar="RAW_NPZ", type=Path)
    parser.add_argument("sidecar", metavar="SIDECAR", type=Path)
    parser.add_argument("map", metavar="MAP", type=Path)
    parser.add_argument("camera", metavar="CAMERA", type=Path)
    parser.add_argument(
        "--checkpoint-manifest",
        required=True,
        type=Path,
        help="Exact upstream checkpoint manifest bytes",
    )
    parser.add_argument(
        "--generation-request",
        required=True,
        type=Path,
        help="Exact upstream generation request bytes",
    )
    parser.add_argument(
        "--document-only",
        action="store_true",
        help="Print only the canonical intake report",
    )


def dispatch_kimodo_pilot_intake_command(
    args: argparse.Namespace,
) -> int | None:
    """Dispatch the audit while redacting file paths and domain failures."""

    if getattr(args, "command", None) != COMMAND:
        return None
    try:
        result = audit_kimodo_pilot_intake_command(
            args.raw_npz,
            args.sidecar,
            args.map,
            args.camera,
            args.checkpoint_manifest,
            args.generation_request,
        )
    except KimodoPilotIntakeCommandError:
        _print({
            "error_code": ERROR_CODE,
            "message": ERROR_MESSAGE,
            "ok": False,
            "status": "error",
        })
        return 2
    if args.document_only:
        _print(result.document)
    else:
        _print({
            "intake": result.document,
            "mode": "audited",
            "ok": True,
        })
    return 0


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ))


__all__ = [
    "COMMAND",
    "ERROR_CODE",
    "ERROR_MESSAGE",
    "add_kimodo_pilot_intake_subcommands",
    "dispatch_kimodo_pilot_intake_command",
]
