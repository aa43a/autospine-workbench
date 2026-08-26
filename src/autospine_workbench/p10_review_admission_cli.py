"""Canonical CLI adapter for P10.4a body-sway review admission."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .p10_review_admission_commands import (
    P10ReviewAdmissionCommandError,
    compile_body_sway_review_admission_command,
)


COMMAND = "compile-body-sway-review-admission"
ERROR_CODE = "body_sway_review_admission_failed"
ERROR_MESSAGE = "Body-sway review admission failed."


def add_p10_review_admission_subcommands(
    subparsers: Any, default_state_root: Path,
) -> None:
    """Register the exact, read-only P10.4a admission command."""

    parser = subparsers.add_parser(
        COMMAND,
        help="Admit the current approved body-sway review head for analysis",
    )
    parser.add_argument("project_id", metavar="PROJECT")
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--decision", type=Path, required=True)
    parser.add_argument("--probe-report", type=Path, required=True)
    for option in _CHAIN_OPTIONS:
        parser.add_argument(option, required=True)
    parser.add_argument("--visual-revision", type=int, required=True)
    parser.add_argument(
        "--state-root", type=Path, default=default_state_root
    )
    parser.add_argument(
        "--document-only", action="store_true",
        help="Print only the canonical BodySwayReviewAdmission document",
    )


def dispatch_p10_review_admission_command(
    args: argparse.Namespace,
) -> int | None:
    """Dispatch P10.4a without exposing input paths or exception details."""

    if getattr(args, "command", None) != COMMAND:
        return None
    try:
        result = compile_body_sway_review_admission_command(
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
            temporary_preview_sha256=args.temporary_preview_sha256,
            runtime_capture_bundle_sha256=
                args.runtime_capture_bundle_sha256,
            capture_artifact_set_sha256=
                args.capture_artifact_set_sha256,
            visual_candidate_sha256=args.visual_candidate_sha256,
            visual_revision=args.visual_revision,
            visual_decision_sha256=args.visual_decision_sha256,
        )
    except P10ReviewAdmissionCommandError:
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
        "status": document["status"],
        "project_id": document["project_id"],
        "clip_id": document["clip_id"],
        "admission_sha256": result.admission_sha256,
        "inputs": {
            "p10_chain": document["source"]["p10_chain"],
            "idle_behavior_candidates_sha256":
                result.idle_behavior_candidates_sha256,
            "idle_behavior_decision_sha256":
                result.idle_behavior_decision_sha256,
            "body_sway_probe_report_sha256":
                result.body_sway_probe_report_sha256,
            "temporary_preview_sha256": result.temporary_preview_sha256,
            "preview_artifact_set_sha256":
                result.preview_artifact_set_sha256,
            "runtime_capture_manifest_sha256":
                result.runtime_capture_manifest_sha256,
            "runtime_capture_bundle_sha256":
                result.runtime_capture_bundle_sha256,
            "capture_artifact_set_sha256":
                result.capture_artifact_set_sha256,
            "visual_candidate_sha256": result.visual_candidate_sha256,
            "visual_revision": result.visual_revision,
            "visual_decision_sha256": result.visual_decision_sha256,
        },
        "claims": document["claims"],
        "release_gate": document["release_gate"],
    }


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))


_CHAIN_OPTIONS = (
    "--layer-manifest-sha256",
    "--p3-rig-sha256",
    "--p3-bundle-sha256",
    "--motion-instance-sha256",
    "--motion-retarget-bundle-sha256",
    "--motion-instance-v2-sha256",
    "--reviewed-motion-bundle-sha256",
    "--temporary-preview-sha256",
    "--runtime-capture-bundle-sha256",
    "--capture-artifact-set-sha256",
    "--visual-candidate-sha256",
    "--visual-decision-sha256",
)
