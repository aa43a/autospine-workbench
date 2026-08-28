"""Canonical CLI adapter for the P10.7c setup golden comparison."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .p10_spine42_v3_setup_regression_commands import (
    P10Spine42V3SetupRegressionCommandError,
    compare_body_sway_spine42_v3_setup_command,
)


COMMAND = "compare-body-sway-spine42-v3-setup-golden"
ERROR_CODE = "body_sway_spine42_v3_setup_regression_failed"
ERROR_MESSAGE = "Body-sway Spine 4.2 v3 setup regression failed."


def add_p10_spine42_v3_setup_regression_subcommands(
    subparsers: Any,
    default_state_root: Path,
) -> None:
    """Register one explicit, read-only setup comparison command."""

    parser = subparsers.add_parser(
        COMMAND,
        help="Compare exact P10 setup captures with approved P6 runtime goldens",
    )
    parser.add_argument(
        "--manifest", type=Path, required=True,
        help="Strict canonical P10.7c comparison request",
    )
    parser.add_argument(
        "--p6-export-contract", type=Path, required=True,
        help="Exact approved P6 export-address contract",
    )
    parser.add_argument(
        "--runtime-golden-contract", type=Path, required=True,
        help="Exact approved P6 runtime screenshot contract",
    )
    parser.add_argument(
        "--state-root", type=Path, default=Path(default_state_root)
    )
    parser.add_argument(
        "--document-only", action="store_true",
        help="Print only the canonical setup regression report",
    )


def dispatch_p10_spine42_v3_setup_regression_command(
    args: argparse.Namespace,
) -> int | None:
    """Return 0 for pass, 1 for a valid regression, and 2 for errors."""

    if getattr(args, "command", None) != COMMAND:
        return None
    try:
        result = compare_body_sway_spine42_v3_setup_command(
            args.state_root,
            args.manifest,
            args.p6_export_contract,
            args.runtime_golden_contract,
        )
    except P10Spine42V3SetupRegressionCommandError:
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
            "mode": "compared",
            "ok": result.status == "passed",
            "request_sha256": result.request_sha256,
            "report_sha256": result.report_sha256,
            "setup_regression": result.document,
            "status": result.status,
        })
    return 0 if result.status == "passed" else 1


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))


__all__ = [
    "COMMAND", "ERROR_CODE", "ERROR_MESSAGE",
    "add_p10_spine42_v3_setup_regression_subcommands",
    "dispatch_p10_spine42_v3_setup_regression_command",
]
