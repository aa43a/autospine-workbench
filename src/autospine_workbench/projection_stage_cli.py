"""Argument and dispatch layer for exact-address P8 projection services."""

from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
import json
from pathlib import Path
from typing import Any

from .projected_motion_commands import (
    ProjectedMotionBundleResult,
    ProjectedMotionCommandError,
    compile_projected_motion_bundle,
    verify_projected_motion_bundle,
)


def add_projection_stage_subcommands(subparsers: Any, state_root: Path) -> None:
    """Register P8 compile and exact replay commands."""

    compile_parser = subparsers.add_parser(
        "compile-projected-motion",
        help="Project one exact Kimodo bundle through an explicit camera",
    )
    compile_parser.add_argument("camera", metavar="CAMERA", type=Path)
    compile_parser.add_argument("--motion-clip-sha256", required=True)
    compile_parser.add_argument("--motion-bundle-sha256", required=True)
    _state_root(compile_parser, state_root)

    verify_parser = subparsers.add_parser(
        "verify-projected-motion",
        help="Replay one exact immutable ProjectedMotionIR bundle",
    )
    verify_parser.add_argument("--projected-motion-sha256", required=True)
    verify_parser.add_argument("--bundle-sha256", required=True)
    _state_root(verify_parser, state_root)


def dispatch_projection_stage_command(args: argparse.Namespace) -> int | None:
    """Dispatch a P8 command, or return ``None`` when unrelated."""

    command = getattr(args, "command", None)
    try:
        if command == "compile-projected-motion":
            result = compile_projected_motion_bundle(
                args.state_root,
                args.camera,
                motion_clip_sha256=args.motion_clip_sha256,
                motion_bundle_sha256=args.motion_bundle_sha256,
            )
        elif command == "verify-projected-motion":
            result = verify_projected_motion_bundle(
                args.state_root,
                args.projected_motion_sha256,
                args.bundle_sha256,
            )
        else:
            return None
    except ProjectedMotionCommandError as exc:
        _print({"ok": False, "status": "error", "error": str(exc)})
        return 2
    payload = _payload(result)
    payload.update(ok=True, status="passed")
    _print(payload)
    return 0


def _payload(result: ProjectedMotionBundleResult) -> dict[str, Any]:
    values = asdict(result) if is_dataclass(result) else vars(result)
    return {
        field: str(value) if field == "path" else value
        for field, value in values.items()
    }


def _state_root(parser: argparse.ArgumentParser, default: Path) -> None:
    parser.add_argument("--state-root", type=Path, default=default)


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
