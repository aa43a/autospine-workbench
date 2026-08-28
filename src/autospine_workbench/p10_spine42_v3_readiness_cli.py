"""Canonical CLI adapter for read-only P10.7 readiness audits."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .p10_spine42_v3_readiness_commands import (
    P10Spine42V3ReadinessCommandError,
    audit_body_sway_spine42_v3_readiness_command,
)


COMMAND = "audit-body-sway-spine42-v3-readiness"
ERROR_CODE = "body_sway_spine42_v3_readiness_audit_failed"
ERROR_MESSAGE = "Body-sway Spine 4.2 v3 readiness audit failed."


def add_p10_spine42_v3_readiness_subcommands(
    subparsers: Any,
    default_state_root: Path,
) -> None:
    """Register one explicit-manifest, zero-write readiness audit."""

    parser = subparsers.add_parser(
        COMMAND,
        help="Audit exact real-sample prerequisites through Spine 4.2 v3",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="Strict canonical readiness request JSON",
    )
    parser.add_argument(
        "--state-root", type=Path, default=Path(default_state_root)
    )
    parser.add_argument(
        "--document-only",
        action="store_true",
        help="Print only the canonical readiness report",
    )


def dispatch_p10_spine42_v3_readiness_command(
    args: argparse.Namespace,
) -> int | None:
    """Dispatch an audit while redacting every underlying failure."""

    if getattr(args, "command", None) != COMMAND:
        return None
    try:
        result = audit_body_sway_spine42_v3_readiness_command(
            args.state_root,
            args.manifest,
        )
    except P10Spine42V3ReadinessCommandError:
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
            "mode": "audited",
            "ok": True,
            "readiness": result.document,
            "request_sha256": result.request_sha256,
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
    "add_p10_spine42_v3_readiness_subcommands",
    "dispatch_p10_spine42_v3_readiness_command",
]
