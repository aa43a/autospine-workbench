"""Canonical isolated CLI adapter for P10.5a seam candidates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .seam_anchor_candidate_commands import (
    SeamAnchorCandidateCommandError,
    compile_seam_anchor_candidates_command,
)


COMMAND = "compile-seam-anchor-candidates"
ERROR_CODE = "seam_anchor_candidates_failed"
ERROR_MESSAGE = "Seam-anchor candidate compilation failed."


def add_seam_anchor_candidate_subcommands(
    subparsers: Any, default_state_root: Path,
) -> None:
    """Register the exact, read-only P10.5a candidate compiler."""

    parser = subparsers.add_parser(
        COMMAND,
        help="Compile review-only static seam anchors from exact P3 inputs",
    )
    parser.add_argument("project_id", metavar="PROJECT")
    parser.add_argument("--layer-manifest-sha256", required=True)
    parser.add_argument("--p3-rig-sha256", required=True)
    parser.add_argument("--p3-bundle-sha256", required=True)
    parser.add_argument(
        "--state-root", type=Path, default=default_state_root
    )
    parser.add_argument(
        "--document-only", action="store_true",
        help="Print only the canonical seam-anchor candidate document",
    )


def dispatch_seam_anchor_candidate_command(
    args: argparse.Namespace,
) -> int | None:
    """Dispatch P10.5a with stable path-free output and errors."""

    if getattr(args, "command", None) != COMMAND:
        return None
    try:
        result = compile_seam_anchor_candidates_command(
            args.state_root,
            args.project_id,
            layer_manifest_sha256=args.layer_manifest_sha256,
            p3_rig_sha256=args.p3_rig_sha256,
            p3_bundle_sha256=args.p3_bundle_sha256,
        )
    except SeamAnchorCandidateCommandError:
        _print({
            "error_code": ERROR_CODE,
            "message": ERROR_MESSAGE,
            "ok": False,
            "status": "error",
        })
        return 2
    _print(result.document if args.document_only else _summary(result))
    return 0


def _summary(result) -> dict[str, Any]:
    document = result.document
    return {
        "ok": True,
        "status": document["summary"]["status"],
        "project_id": document["project_id"],
        "seam_anchor_candidates_sha256": (
            result.seam_anchor_candidates_sha256
        ),
        "summary": document["summary"],
        "claims": document["claims"],
        "release_gate": document["release_gate"],
    }


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))
