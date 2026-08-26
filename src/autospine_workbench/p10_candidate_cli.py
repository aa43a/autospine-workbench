"""CLI registration and canonical output for P10 candidates."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from .p10_candidate_commands import (
    P10CandidateCommandError,
    compile_idle_behavior_candidates_command,
)


def add_p10_candidate_subcommands(
    subparsers: Any, default_state_root: Path
) -> None:
    """Register the read-only exact-address P10 compiler."""

    parser = subparsers.add_parser(
        "compile-idle-behavior-candidates",
        help="Compile candidate-only idle behaviors from exact P3/P5/P9",
    )
    parser.add_argument("project_id", metavar="PROJECT")
    parser.add_argument("--layer-manifest-sha256", required=True)
    parser.add_argument("--p3-rig-sha256", required=True)
    parser.add_argument("--p3-bundle-sha256", required=True)
    parser.add_argument("--motion-instance-sha256", required=True)
    parser.add_argument("--motion-retarget-bundle-sha256", required=True)
    parser.add_argument("--motion-instance-v2-sha256", required=True)
    parser.add_argument("--reviewed-motion-bundle-sha256", required=True)
    parser.add_argument(
        "--state-root", type=Path, default=default_state_root
    )
    parser.add_argument(
        "--document-only",
        action="store_true",
        help="Print only the canonical idle-behavior candidate document",
    )


def dispatch_p10_candidate_command(args: argparse.Namespace) -> int | None:
    """Dispatch P10, returning ``None`` for unrelated commands."""

    if getattr(args, "command", None) != \
            "compile-idle-behavior-candidates":
        return None
    try:
        result = compile_idle_behavior_candidates_command(
            args.state_root,
            args.project_id,
            layer_manifest_sha256=args.layer_manifest_sha256,
            p3_rig_sha256=args.p3_rig_sha256,
            p3_bundle_sha256=args.p3_bundle_sha256,
            motion_instance_sha256=args.motion_instance_sha256,
            motion_retarget_bundle_sha256=(
                args.motion_retarget_bundle_sha256
            ),
            motion_instance_v2_sha256=args.motion_instance_v2_sha256,
            reviewed_motion_bundle_sha256=(
                args.reviewed_motion_bundle_sha256
            ),
        )
    except P10CandidateCommandError as exc:
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
