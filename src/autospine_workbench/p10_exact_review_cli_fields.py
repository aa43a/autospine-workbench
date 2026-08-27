"""Shared explicit CLI fields for commands rooted at one P10 review head."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any


CHAIN_OPTIONS = (
    "--layer-manifest-sha256", "--p3-rig-sha256", "--p3-bundle-sha256",
    "--motion-instance-sha256", "--motion-retarget-bundle-sha256",
    "--motion-instance-v2-sha256", "--reviewed-motion-bundle-sha256",
    "--temporary-preview-sha256", "--runtime-capture-bundle-sha256",
    "--capture-artifact-set-sha256", "--visual-candidate-sha256",
    "--visual-decision-sha256",
)


def add_exact_review_arguments(
    parser: argparse.ArgumentParser, default_state_root: Path,
) -> None:
    """Add the sole explicit P10 source-address and current-head fields."""

    parser.add_argument("project_id", metavar="PROJECT")
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--decision", type=Path, required=True)
    parser.add_argument("--probe-report", type=Path, required=True)
    for option in CHAIN_OPTIONS:
        parser.add_argument(option, required=True)
    parser.add_argument("--visual-revision", type=int, required=True)
    parser.add_argument("--state-root", type=Path, default=default_state_root)


def exact_review_command_kwargs(args: Any) -> dict[str, Any]:
    """Map parsed fields to the exact command API without discovery."""

    return {
        "layer_manifest_sha256": args.layer_manifest_sha256,
        "p3_rig_sha256": args.p3_rig_sha256,
        "p3_bundle_sha256": args.p3_bundle_sha256,
        "motion_instance_sha256": args.motion_instance_sha256,
        "motion_retarget_bundle_sha256": args.motion_retarget_bundle_sha256,
        "motion_instance_v2_sha256": args.motion_instance_v2_sha256,
        "reviewed_motion_bundle_sha256": args.reviewed_motion_bundle_sha256,
        "temporary_preview_sha256": args.temporary_preview_sha256,
        "runtime_capture_bundle_sha256": args.runtime_capture_bundle_sha256,
        "capture_artifact_set_sha256": args.capture_artifact_set_sha256,
        "visual_candidate_sha256": args.visual_candidate_sha256,
        "visual_revision": args.visual_revision,
        "visual_decision_sha256": args.visual_decision_sha256,
    }
