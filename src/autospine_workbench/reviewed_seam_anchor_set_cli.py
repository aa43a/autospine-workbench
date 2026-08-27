"""Canonical CLI adapter for P10.5c reviewed seam-anchor sets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .reviewed_seam_anchor_set_commands import (
    ReviewedSeamAnchorSetCommandError,
    compile_reviewed_seam_anchor_set_command,
    verify_reviewed_seam_anchor_set_command,
)


COMPILE_COMMAND = "compile-reviewed-seam-anchor-set"
VERIFY_COMMAND = "verify-reviewed-seam-anchor-set"
COMPILE_ERROR_CODE = "reviewed_seam_anchor_set_compile_failed"
VERIFY_ERROR_CODE = "reviewed_seam_anchor_set_verify_failed"


def add_reviewed_seam_anchor_set_subcommands(
    subparsers: Any, default_state_root: Path,
) -> None:
    """Register strict explicit compile and verify addresses."""

    compile_parser = subparsers.add_parser(
        COMPILE_COMMAND,
        help="Compile the exact current seam-review head into a static set",
    )
    compile_parser.add_argument("project_id", metavar="PROJECT")
    compile_parser.add_argument("--layer-manifest-sha256", required=True)
    compile_parser.add_argument("--p3-rig-sha256", required=True)
    compile_parser.add_argument("--p3-bundle-sha256", required=True)
    compile_parser.add_argument("--candidate-sha256", required=True)
    compile_parser.add_argument(
        "--review-revision", required=True, type=_positive_revision
    )
    compile_parser.add_argument("--decision-sha256", required=True)
    _state_root(compile_parser, default_state_root)

    verify_parser = subparsers.add_parser(
        VERIFY_COMMAND,
        help="Verify one exact historical reviewed seam-anchor set bundle",
    )
    verify_parser.add_argument("project_id", metavar="PROJECT")
    verify_parser.add_argument("--reviewed-set-sha256", required=True)
    verify_parser.add_argument("--bundle-sha256", required=True)
    _state_root(verify_parser, default_state_root)


def dispatch_reviewed_seam_anchor_set_command(
    args: argparse.Namespace,
) -> int | None:
    """Dispatch P10.5c with stable path-free JSON responses."""

    command = getattr(args, "command", None)
    if command not in {COMPILE_COMMAND, VERIFY_COMMAND}:
        return None
    try:
        if command == COMPILE_COMMAND:
            result = compile_reviewed_seam_anchor_set_command(
                args.state_root,
                args.project_id,
                layer_manifest_sha256=args.layer_manifest_sha256,
                p3_rig_sha256=args.p3_rig_sha256,
                p3_bundle_sha256=args.p3_bundle_sha256,
                candidate_sha256=args.candidate_sha256,
                review_revision=args.review_revision,
                decision_sha256=args.decision_sha256,
            )
        else:
            result = verify_reviewed_seam_anchor_set_command(
                args.state_root,
                args.project_id,
                reviewed_set_sha256=args.reviewed_set_sha256,
                bundle_sha256=args.bundle_sha256,
            )
    except ReviewedSeamAnchorSetCommandError:
        compile_mode = command == COMPILE_COMMAND
        _print({
            "error_code": (
                COMPILE_ERROR_CODE if compile_mode else VERIFY_ERROR_CODE
            ),
            "message": (
                "Reviewed seam-anchor set compilation failed."
                if compile_mode
                else "Reviewed seam-anchor set verification failed."
            ),
            "ok": False,
            "status": "error",
        })
        return 2
    _print(_payload(result))
    return 0


def _payload(result) -> dict[str, Any]:
    return {
        "ok": True,
        "status": result.mode,
        "project_id": result.project_id,
        "source": result.source,
        "output": result.output,
        "artifact_status": result.artifact_status,
        "release_gate": {
            "status": result.release_gate_status,
            "reason_codes": list(result.release_gate_reason_codes),
        },
        "summary": {
            "relationship_count": result.relationship_count,
            "anchor_pair_count": result.anchor_pair_count,
        },
        "head_observation": result.head_observation,
    }


def _positive_revision(value: str) -> int:
    try:
        revision = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "review revision must be a positive integer"
        ) from exc
    if revision < 1:
        raise argparse.ArgumentTypeError(
            "review revision must be a positive integer"
        )
    return revision


def _state_root(parser: argparse.ArgumentParser, default: Path) -> None:
    parser.add_argument("--state-root", type=Path, default=Path(default))


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ))
