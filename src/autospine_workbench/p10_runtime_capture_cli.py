"""CLI surface for licensed P10 official-runtime capture publication."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .p10_runtime_capture_commands import (
    P10RuntimeCaptureCommandError,
    capture_body_sway_runtime_command,
)


COMMAND = "capture-body-sway-runtime"
CAPTURE_ERROR_CODE = "body_sway_runtime_capture_failed"
CAPTURE_ERROR_MESSAGE = (
    "Body-sway runtime capture failed; no evidence was published."
)
LICENSE_ACKNOWLEDGEMENT_ENV = (
    "AUTOSPINE_SPINE42_RUNTIME_LICENSE_ACKNOWLEDGED"
)


def add_p10_runtime_capture_subcommands(
    subparsers: Any, default_state_root: Path,
) -> None:
    """Register the explicit-license official-runtime capture command."""

    parser = subparsers.add_parser(
        COMMAND,
        help="Capture and seal unreviewed body-sway evidence with Spine 4.2",
    )
    parser.add_argument("project_id", metavar="PROJECT")
    for option in _EXACT_OPTIONS:
        parser.add_argument(option, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--decision", type=Path, required=True)
    parser.add_argument("--probe-report", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--browser-executable", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, default=default_state_root)
    parser.add_argument(
        "--acknowledge-spine-runtime-license",
        action="store_true",
        help=(
            "Confirm authorization to use the supplied Spine runtime; "
            f"alternatively set {LICENSE_ACKNOWLEDGEMENT_ENV}=1"
        ),
    )


def dispatch_p10_runtime_capture_command(
    args: argparse.Namespace,
) -> int | None:
    """Dispatch the capture command, with bounded canonical JSON output."""

    if getattr(args, "command", None) != COMMAND:
        return None
    acknowledged = (
        args.acknowledge_spine_runtime_license
        or os.environ.get(LICENSE_ACKNOWLEDGEMENT_ENV) == "1"
    )
    try:
        result = capture_body_sway_runtime_command(
            args.state_root,
            args.project_id,
            args.candidates,
            args.decision,
            args.probe_report,
            layer_manifest_sha256=args.layer_manifest_sha256,
            p3_rig_sha256=args.p3_rig_sha256,
            p3_bundle_sha256=args.p3_bundle_sha256,
            motion_instance_sha256=args.motion_instance_sha256,
            motion_retarget_bundle_sha256=
                args.motion_retarget_bundle_sha256,
            motion_instance_v2_sha256=args.motion_instance_v2_sha256,
            reviewed_motion_bundle_sha256=
                args.reviewed_motion_bundle_sha256,
            runtime_root=args.runtime_root,
            browser_executable=args.browser_executable,
            license_acknowledged=acknowledged,
        )
    except P10RuntimeCaptureCommandError:
        _print({
            "error_code": CAPTURE_ERROR_CODE,
            "message": CAPTURE_ERROR_MESSAGE,
            "ok": False,
            "status": "error",
        })
        return 2
    _print({
        "ok": True,
        "status": "captured_unreviewed",
        "release_gate": {
            "status": result.release_gate_status,
            "reason_codes": list(result.release_gate_reason_codes),
        },
        "path": str(result.path),
        "temporary_preview_sha256": result.temporary_preview_sha256,
        "runtime_capture_sha256": result.runtime_capture_sha256,
        "artifact_set_sha256": result.artifact_set_sha256,
        "bundle_sha256": result.bundle_sha256,
        "case_count": result.case_count,
        "browser_family": result.browser_family,
        "browser_reported_version": result.browser_reported_version,
        "reused": result.reused,
    })
    return 0


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))


_EXACT_OPTIONS = (
    "--layer-manifest-sha256",
    "--p3-rig-sha256",
    "--p3-bundle-sha256",
    "--motion-instance-sha256",
    "--motion-retarget-bundle-sha256",
    "--motion-instance-v2-sha256",
    "--reviewed-motion-bundle-sha256",
)
