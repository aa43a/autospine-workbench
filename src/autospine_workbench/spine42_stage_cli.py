"""Argument and JSON dispatch layer for exact P6 Spine 4.2 services."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from .spine42_commands import (
    Spine42CommandError,
    compile_spine42_bundle,
    verify_spine42_bundle,
)


def add_spine42_stage_subcommands(
    subparsers: Any, default_state_root: Path,
) -> None:
    """Register exact-address P6 compile and verify commands."""

    compile_export = subparsers.add_parser(
        "compile-spine42",
        help="Compile one exact P3 or P3/P5 chain to a verified Spine 4.2 bundle",
    )
    compile_export.add_argument("project_id", metavar="PROJECT")
    compile_export.add_argument("--p3-rig-sha256", required=True)
    compile_export.add_argument("--p3-bundle-sha256", required=True)
    compile_export.add_argument("--motion-instance-sha256")
    compile_export.add_argument("--motion-bundle-sha256")
    _add_state_root(compile_export, default_state_root)

    verify_export = subparsers.add_parser(
        "verify-spine42",
        help="Verify one exact Spine 4.2 bundle and rebuild its upstream chain",
    )
    verify_export.add_argument("project_id", metavar="PROJECT")
    verify_export.add_argument("--skeleton-json-sha256", required=True)
    verify_export.add_argument("--bundle-sha256", required=True)
    _add_state_root(verify_export, default_state_root)


def dispatch_spine42_stage_command(args: argparse.Namespace) -> int | None:
    """Dispatch a P6 command, returning ``None`` for another namespace."""

    command = getattr(args, "command", None)
    if command == "compile-spine42":
        return _run(
            compile_spine42_bundle,
            args.state_root,
            args.project_id,
            p3_rig_sha256=args.p3_rig_sha256,
            p3_bundle_sha256=args.p3_bundle_sha256,
            motion_instance_sha256=args.motion_instance_sha256,
            motion_bundle_sha256=args.motion_bundle_sha256,
        )
    if command == "verify-spine42":
        return _run(
            verify_spine42_bundle,
            args.state_root,
            args.project_id,
            skeleton_json_sha256=args.skeleton_json_sha256,
            bundle_sha256=args.bundle_sha256,
        )
    return None


def _run(
    service: Callable[..., Any], *positional: Any, **keywords: Any,
) -> int:
    try:
        response = _payload(service(*positional, **keywords))
        response.update(ok=True, status="passed")
    except Spine42CommandError as exc:
        _print({"ok": False, "status": "error", "error": str(exc)})
        return 2
    _print(response)
    return 0


def _payload(result: Any) -> dict[str, Any]:
    return {
        "path": str(result.path),
        "project_id": result.project_id,
        "mode": result.mode,
        "clip_id": result.clip_id,
        "source_addresses": dict(result.source_addresses),
        "output_sha256s": dict(result.output_sha256s),
        "skeleton_json_sha256": result.skeleton_json_sha256,
        "atlas_sha256": result.atlas_sha256,
        "png_sha256": result.png_sha256,
        "run_identity_sha256": result.run_identity_sha256,
        "run_document_sha256": result.run_document_sha256,
        "report_sha256": result.report_sha256,
        "bundle_sha256": result.bundle_sha256,
        "summary": result.summary,
        "reused": result.reused,
    }


def _add_state_root(parser: argparse.ArgumentParser, default: Path) -> None:
    parser.add_argument("--state-root", type=Path, default=Path(default))


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(
        value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True,
    ))
