"""CLI registration and canonical output for reviewed-motion bundles."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from .p9_bundle_commands import (
    P9BundleCommandError,
    publish_reviewed_motion_bundle_command,
    verify_reviewed_motion_bundle_command,
)


def add_p9_bundle_subcommands(subparsers: Any, state_root: Path) -> None:
    """Register immutable reviewed-motion publication and replay commands."""

    publish = subparsers.add_parser(
        "publish-reviewed-motion-bundle",
        help="Compile MotionInstance v2 and publish one exact P9 bundle",
    )
    publish.add_argument("project_id", metavar="PROJECT")
    publish.add_argument("--foot-candidates", type=Path, required=True)
    publish.add_argument("--depth-candidates", type=Path, required=True)
    publish.add_argument("--decision", type=Path, required=True)
    publish.add_argument("--reviewed-policy", type=Path, required=True)
    publish.add_argument("--p3-rig-sha256", required=True)
    publish.add_argument("--p3-bundle-sha256", required=True)
    publish.add_argument("--motion-instance-sha256", required=True)
    publish.add_argument(
        "--motion-retarget-bundle-sha256", required=True
    )
    _common(publish, state_root)

    verify = subparsers.add_parser(
        "verify-reviewed-motion-bundle",
        help="Replay one exact immutable P9 reviewed-motion bundle",
    )
    verify.add_argument("project_id", metavar="PROJECT")
    verify.add_argument("--motion-instance-v2-sha256", required=True)
    verify.add_argument(
        "--reviewed-motion-bundle-sha256", required=True
    )
    _common(verify, state_root)


def dispatch_p9_bundle_command(args: argparse.Namespace) -> int | None:
    """Dispatch one P9.6 bundle command or ignore unrelated namespaces."""

    command = getattr(args, "command", None)
    try:
        if command == "publish-reviewed-motion-bundle":
            result = publish_reviewed_motion_bundle_command(
                args.state_root,
                args.project_id,
                args.foot_candidates,
                args.depth_candidates,
                args.decision,
                args.reviewed_policy,
                p3_rig_sha256=args.p3_rig_sha256,
                p3_bundle_sha256=args.p3_bundle_sha256,
                motion_instance_sha256=args.motion_instance_sha256,
                motion_retarget_bundle_sha256=(
                    args.motion_retarget_bundle_sha256
                ),
            )
        elif command == "verify-reviewed-motion-bundle":
            result = verify_reviewed_motion_bundle_command(
                args.state_root,
                args.project_id,
                motion_instance_v2_sha256=(
                    args.motion_instance_v2_sha256
                ),
                reviewed_motion_bundle_sha256=(
                    args.reviewed_motion_bundle_sha256
                ),
            )
        else:
            return None
    except P9BundleCommandError as exc:
        _print({"error": str(exc), "ok": False, "status": "error"})
        return 2
    if args.document_only:
        _print(result.report)
        return 0
    payload = _jsonable(asdict(result))
    payload.update(ok=True, status="passed")
    _print(payload)
    return 0


def _common(parser: argparse.ArgumentParser, state_root: Path) -> None:
    parser.add_argument("--state-root", type=Path, default=state_root)
    parser.add_argument(
        "--document-only", action="store_true",
        help="Print only the canonical report and explicit address",
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
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ))
