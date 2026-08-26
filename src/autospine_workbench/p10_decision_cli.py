"""CLI registration and canonical output for P10 decisions."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from .p10_decision_commands import (
    P10DecisionCommandError,
    compile_idle_behavior_decision_command,
)


def add_p10_decision_subcommands(subparsers: Any) -> None:
    """Register the state-free idle-behavior decision compiler."""

    parser = subparsers.add_parser(
        "compile-idle-behavior-decision",
        help="Bind explicit human review to exact idle candidates",
    )
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--review-input", type=Path, required=True)
    parser.add_argument(
        "--document-only",
        action="store_true",
        help="Print only the canonical idle-behavior decision document",
    )


def dispatch_p10_decision_command(args: argparse.Namespace) -> int | None:
    """Dispatch P10 decision compilation or ignore unrelated commands."""

    if getattr(args, "command", None) != "compile-idle-behavior-decision":
        return None
    try:
        result = compile_idle_behavior_decision_command(
            args.candidates, args.review_input
        )
    except P10DecisionCommandError as exc:
        _print({"error": str(exc), "ok": False, "status": "error"})
        return 2
    if args.document_only:
        _print(result.document)
        return 0
    payload = _jsonable(asdict(result))
    payload.update(ok=True, status="passed")
    _print(payload)
    return 0


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
