"""Canonical CLI adapter for P10.4b2 continuous preview-model proof."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .p10_continuous_proof_commands import (
    P10ContinuousProofCommandError,
    compile_body_sway_continuous_proof_command,
)
from .p10_exact_review_cli_fields import (
    add_exact_review_arguments,
    exact_review_command_kwargs,
)


COMMAND = "compile-body-sway-continuous-proof"
ERROR_CODE = "body_sway_continuous_proof_failed"
ERROR_MESSAGE = "Body-sway continuous proof compilation failed."


def add_p10_continuous_proof_subcommands(
    subparsers: Any, default_state_root: Path,
) -> None:
    """Register the exact, read-only P10.4b2 proof command."""

    parser = subparsers.add_parser(
        COMMAND,
        help="Prove the closed unit gain over sampled-linear preview segments",
    )
    add_exact_review_arguments(parser, default_state_root)
    parser.add_argument(
        "--document-only", action="store_true",
        help="Print only the canonical continuous preview-model proof",
    )


def dispatch_p10_continuous_proof_command(
    args: argparse.Namespace,
) -> int | None:
    """Dispatch P10.4b2 with stable path-free output and errors."""

    if getattr(args, "command", None) != COMMAND:
        return None
    try:
        result = compile_body_sway_continuous_proof_command(
            args.state_root, args.project_id,
            args.candidates, args.decision, args.probe_report,
            **exact_review_command_kwargs(args),
        )
    except P10ContinuousProofCommandError:
        _print({
            "error_code": ERROR_CODE, "message": ERROR_MESSAGE,
            "ok": False, "status": "error",
        })
        return 2
    _print(result.document if args.document_only else _summary(result))
    return 0


def _summary(result) -> dict[str, Any]:
    document = result.document
    return {
        "ok": True,
        "status": document["status"],
        "project_id": result.project_id,
        "clip_id": result.clip_id,
        "continuous_proof_sha256": result.continuous_proof_sha256,
        "amplitude_envelope_sha256": result.amplitude_envelope_sha256,
        "preview_projection_sha256": result.preview_projection_sha256,
        "visual_candidate_sha256": result.visual_candidate_sha256,
        "visual_revision": result.visual_revision,
        "visual_decision_sha256": result.visual_decision_sha256,
        "summary": document["summary"],
        "claims": document["claims"],
        "release_gate": document["release_gate"],
    }


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))
