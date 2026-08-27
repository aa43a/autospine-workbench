"""Canonical CLI adapter for sampled P10.7b raster review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .p10_spine42_v3_raster_review_commands import (
    P10Spine42V3RasterReviewCommandError,
    prepare_spine42_v3_raster_review_command,
    submit_spine42_v3_raster_review_command,
)


PREPARE_COMMAND = "prepare-body-sway-spine42-v3-raster-review"
SUBMIT_COMMAND = "submit-body-sway-spine42-v3-raster-review"
PREPARE_ERROR_CODE = "body_sway_spine42_v3_raster_review_prepare_failed"
SUBMIT_ERROR_CODE = "body_sway_spine42_v3_raster_review_submit_failed"
PREPARE_ERROR_MESSAGE = "Spine 4.2 v3 raster review preparation failed."
SUBMIT_ERROR_MESSAGE = "Spine 4.2 v3 raster review submission failed."


def add_p10_spine42_v3_raster_review_subcommands(
    subparsers: Any, default_state_root: Path,
) -> None:
    """Register exact candidate preparation and decision compilation."""

    prepare = subparsers.add_parser(
        PREPARE_COMMAND,
        help="Prepare exact sampled Spine 4.2 raster evidence for review",
    )
    prepare.add_argument("project_id", metavar="PROJECT")
    prepare.add_argument("--spine42-v3-bundle-sha256", required=True)
    prepare.add_argument("--capture-bundle-sha256", required=True)
    prepare.add_argument(
        "--state-root", type=Path, default=Path(default_state_root)
    )

    submit = subparsers.add_parser(
        SUBMIT_COMMAND,
        help="Compile one exhaustive human decision without publication",
    )
    submit.add_argument("project_id", metavar="PROJECT")
    submit.add_argument("--spine42-v3-bundle-sha256", required=True)
    submit.add_argument("--capture-bundle-sha256", required=True)
    submit.add_argument("--candidate", type=Path, required=True)
    submit.add_argument("--review-input", type=Path, required=True)
    submit.add_argument("--previous-decision", type=Path)
    submit.add_argument(
        "--state-root", type=Path, default=Path(default_state_root)
    )


def dispatch_p10_spine42_v3_raster_review_command(
    args: argparse.Namespace,
) -> int | None:
    """Dispatch review commands with canonical documents and fixed errors."""

    command = getattr(args, "command", None)
    if command not in {PREPARE_COMMAND, SUBMIT_COMMAND}:
        return None
    prepare_mode = command == PREPARE_COMMAND
    try:
        if prepare_mode:
            result = prepare_spine42_v3_raster_review_command(
                args.state_root, args.project_id,
                spine42_v3_bundle_sha256=args.spine42_v3_bundle_sha256,
                capture_bundle_sha256=args.capture_bundle_sha256,
            )
        else:
            result = submit_spine42_v3_raster_review_command(
                args.state_root, args.project_id,
                args.candidate, args.review_input,
                spine42_v3_bundle_sha256=args.spine42_v3_bundle_sha256,
                capture_bundle_sha256=args.capture_bundle_sha256,
                previous_decision_path=args.previous_decision,
            )
    except P10Spine42V3RasterReviewCommandError:
        _print({
            "error_code": (
                PREPARE_ERROR_CODE if prepare_mode else SUBMIT_ERROR_CODE
            ),
            "message": (
                PREPARE_ERROR_MESSAGE if prepare_mode
                else SUBMIT_ERROR_MESSAGE
            ),
            "ok": False, "status": "error",
        })
        return 2
    _print(result.document)
    return 0


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))


__all__ = [
    "PREPARE_COMMAND", "SUBMIT_COMMAND",
    "add_p10_spine42_v3_raster_review_subcommands",
    "dispatch_p10_spine42_v3_raster_review_command",
]
