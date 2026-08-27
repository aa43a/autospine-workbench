"""Canonical CLI adapter for official P10.7b Spine runtime capture."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .p10_spine42_v3_runtime_commands import (
    P10Spine42V3RuntimeCommandError,
    capture_body_sway_spine42_v3_runtime_command,
    verify_body_sway_spine42_v3_runtime_command,
)


CAPTURE_COMMAND = "capture-body-sway-spine42-v3-runtime"
VERIFY_COMMAND = "verify-body-sway-spine42-v3-runtime"
CAPTURE_ERROR_CODE = "body_sway_spine42_v3_runtime_capture_failed"
VERIFY_ERROR_CODE = "body_sway_spine42_v3_runtime_verify_failed"
CAPTURE_ERROR_MESSAGE = "Body-sway Spine 4.2 v3 runtime capture failed."
VERIFY_ERROR_MESSAGE = "Body-sway Spine 4.2 v3 runtime verification failed."
LICENSE_ACKNOWLEDGEMENT_ENV = (
    "AUTOSPINE_SPINE42_RUNTIME_LICENSE_ACKNOWLEDGED"
)


def add_p10_spine42_v3_runtime_subcommands(
    subparsers: Any, default_state_root: Path,
) -> None:
    """Register exact capture and historical verification commands."""

    capture = subparsers.add_parser(
        CAPTURE_COMMAND,
        help="Capture sampled evidence with an authorized Spine 4.2 runtime",
    )
    capture.add_argument("project_id", metavar="PROJECT")
    capture.add_argument("--skeleton-json-sha256", required=True)
    capture.add_argument("--spine42-v3-bundle-sha256", required=True)
    capture.add_argument("--runtime-root", type=Path, required=True)
    capture.add_argument("--browser-executable", type=Path, required=True)
    capture.add_argument(
        "--acknowledge-spine-runtime-license", action="store_true",
        help=(
            "Confirm authorization to use the supplied Spine runtime; "
            f"alternatively set {LICENSE_ACKNOWLEDGEMENT_ENV}=1"
        ),
    )
    _state_root(capture, default_state_root)

    verify = subparsers.add_parser(
        VERIFY_COMMAND,
        help="Verify one exact historical Spine 4.2 v3 capture bundle",
    )
    verify.add_argument("project_id", metavar="PROJECT")
    verify.add_argument("--spine42-v3-bundle-sha256", required=True)
    verify.add_argument("--capture-bundle-sha256", required=True)
    _state_root(verify, default_state_root)


def dispatch_p10_spine42_v3_runtime_command(
    args: argparse.Namespace,
) -> int | None:
    """Dispatch P10.7b with a fail-closed license gate and fixed errors."""

    command = getattr(args, "command", None)
    if command not in {CAPTURE_COMMAND, VERIFY_COMMAND}:
        return None
    capture_mode = command == CAPTURE_COMMAND
    acknowledged = capture_mode and (
        args.acknowledge_spine_runtime_license
        or os.environ.get(LICENSE_ACKNOWLEDGEMENT_ENV) == "1"
    )
    if capture_mode and not acknowledged:
        _print(_failure(True))
        return 2
    try:
        if capture_mode:
            result = capture_body_sway_spine42_v3_runtime_command(
                args.state_root, args.project_id,
                skeleton_json_sha256=args.skeleton_json_sha256,
                spine42_v3_bundle_sha256=args.spine42_v3_bundle_sha256,
                runtime_root=args.runtime_root,
                browser_executable=args.browser_executable,
                license_acknowledged=True,
            )
        else:
            result = verify_body_sway_spine42_v3_runtime_command(
                args.state_root, args.project_id,
                spine42_v3_bundle_sha256=args.spine42_v3_bundle_sha256,
                capture_bundle_sha256=args.capture_bundle_sha256,
            )
    except P10Spine42V3RuntimeCommandError:
        _print(_failure(capture_mode))
        return 2
    _print(_success(result))
    return 0


def _success(result) -> dict[str, Any]:
    return {
        "ok": True, "status": result.mode,
        "path": str(result.path),
        "project_id": result.project_id, "clip_id": result.clip_id,
        "address": {
            "skeleton_json_sha256": result.skeleton_json_sha256,
            "spine42_v3_bundle_sha256": result.spine42_v3_bundle_sha256,
            "capture_bundle_sha256": result.capture_bundle_sha256,
        },
        "capture_plan_sha256": result.capture_plan_sha256,
        "raster_metrics_sha256": result.raster_metrics_sha256,
        "manifest_sha256": result.manifest_sha256,
        "browser": {
            "family": result.browser_family,
            "reported_version": result.browser_reported_version,
        },
        "summary": {
            "case_count": result.case_count,
            "attachment_count": result.attachment_count,
            "artifact_count": result.artifact_count,
            "metrics_status": result.metrics_status,
        },
        "release_gate": {"status": result.release_gate_status},
        "reused": result.reused,
    }


def _failure(capture_mode: bool) -> dict[str, Any]:
    return {
        "error_code": CAPTURE_ERROR_CODE if capture_mode else VERIFY_ERROR_CODE,
        "message": (
            CAPTURE_ERROR_MESSAGE if capture_mode else VERIFY_ERROR_MESSAGE
        ),
        "ok": False, "status": "error",
    }


def _state_root(parser: argparse.ArgumentParser, default: Path) -> None:
    parser.add_argument("--state-root", type=Path, default=Path(default))


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))


__all__ = [
    "CAPTURE_COMMAND", "VERIFY_COMMAND", "LICENSE_ACKNOWLEDGEMENT_ENV",
    "add_p10_spine42_v3_runtime_subcommands",
    "dispatch_p10_spine42_v3_runtime_command",
]
