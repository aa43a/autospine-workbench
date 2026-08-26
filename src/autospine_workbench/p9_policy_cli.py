"""CLI registration and dispatch for explicit P9 review compilation."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from .p9_policy_commands import (
    P9PolicyCommandError,
    compile_motion_policy_decision_command,
    compile_reviewed_motion_policy_command,
)


def add_p9_policy_subcommands(subparsers: Any, state_root: Path) -> None:
    decision = subparsers.add_parser(
        "compile-motion-policy-decision",
        help="Bind explicit human choices to exact P9 candidate reports",
    )
    _review_files(decision)
    _document_only(decision)

    policy = subparsers.add_parser(
        "compile-reviewed-motion-policy",
        help="Compile approved P9 decisions into runtime-neutral timelines",
    )
    policy.add_argument("project_id", metavar="PROJECT")
    _review_files(policy, include_review=False)
    policy.add_argument("--decision", type=Path, required=True)
    policy.add_argument("--p3-rig-sha256", required=True)
    policy.add_argument("--p3-bundle-sha256", required=True)
    _document_only(policy)
    policy.add_argument("--state-root", type=Path, default=state_root)


def dispatch_p9_policy_command(args: argparse.Namespace) -> int | None:
    command = getattr(args, "command", None)
    try:
        if command == "compile-motion-policy-decision":
            result = compile_motion_policy_decision_command(
                args.foot_candidates,
                args.depth_candidates,
                args.review_input,
            )
        elif command == "compile-reviewed-motion-policy":
            result = compile_reviewed_motion_policy_command(
                args.state_root,
                args.project_id,
                args.foot_candidates,
                args.depth_candidates,
                args.decision,
                p3_rig_sha256=args.p3_rig_sha256,
                p3_bundle_sha256=args.p3_bundle_sha256,
            )
        else:
            return None
    except P9PolicyCommandError as exc:
        _print({"error": str(exc), "ok": False, "status": "error"})
        return 2
    if args.document_only:
        _print(result.report)
        return 0
    payload = _jsonable(asdict(result))
    payload.update(ok=True, status="passed")
    _print(payload)
    return 0


def _review_files(parser, *, include_review: bool = True) -> None:
    parser.add_argument("--foot-candidates", type=Path, required=True)
    parser.add_argument("--depth-candidates", type=Path, required=True)
    if include_review:
        parser.add_argument("--review-input", type=Path, required=True)


def _document_only(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--document-only", action="store_true",
        help="Print only the canonical document for pipeline handoff",
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
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))
