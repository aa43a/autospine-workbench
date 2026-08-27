"""Argument and dispatch layer for exact-address P8/P9 services."""

from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
import json
from pathlib import Path
from typing import Any

from .projected_motion_commands import (
    ProjectedMotionCommandError,
    compile_projected_motion_bundle,
    probe_projected_scale,
    verify_projected_motion_bundle,
)
from .p9_readonly_cli import (
    add_p9_readonly_subcommands,
    dispatch_p9_readonly_command,
)
from .p9_policy_cli import (
    add_p9_policy_subcommands,
    dispatch_p9_policy_command,
)
from .p9_bundle_cli import (
    add_p9_bundle_subcommands,
    dispatch_p9_bundle_command,
)
from .p9_v2_cli import add_p9_v2_subcommands, dispatch_p9_v2_command
from .p10_candidate_cli import (
    add_p10_candidate_subcommands,
    dispatch_p10_candidate_command,
)
from .p10_decision_cli import (
    add_p10_decision_subcommands,
    dispatch_p10_decision_command,
)
from .p10_probe_cli import (
    add_p10_probe_subcommands,
    dispatch_p10_probe_command,
)
from .p10_preview_cli import (
    add_p10_preview_subcommands,
    dispatch_p10_preview_command,
)
from .p10_runtime_capture_cli import (
    add_p10_runtime_capture_subcommands,
    dispatch_p10_runtime_capture_command,
)
from .p10_visual_review_cli import (
    add_p10_visual_review_subcommands,
    dispatch_p10_visual_review_command,
)
from .p10_review_admission_cli import (
    add_p10_review_admission_subcommands,
    dispatch_p10_review_admission_command,
)
from .p10_amplitude_envelope_cli import (
    add_p10_amplitude_envelope_subcommands,
    dispatch_p10_amplitude_envelope_command,
)
from .p10_continuous_proof_cli import (
    add_p10_continuous_proof_subcommands,
    dispatch_p10_continuous_proof_command,
)
from .p10_dynamic_seam_cli import (
    add_p10_dynamic_seam_subcommands,
    dispatch_p10_dynamic_seam_command,
)
from .p10_motion_consumer_admission_cli import (
    add_p10_motion_consumer_admission_subcommands,
    dispatch_p10_motion_consumer_admission_command,
)
from .p10_motion_instance_v3_cli import (
    add_p10_motion_instance_v3_subcommands,
    dispatch_p10_motion_instance_v3_command,
)
from .p10_spine42_v3_cli import (
    add_p10_spine42_v3_subcommands,
    dispatch_p10_spine42_v3_command,
)
from .p10_spine42_v3_raster_review_cli import (
    add_p10_spine42_v3_raster_review_subcommands,
    dispatch_p10_spine42_v3_raster_review_command,
)
from .p10_spine42_v3_runtime_cli import (
    add_p10_spine42_v3_runtime_subcommands,
    dispatch_p10_spine42_v3_runtime_command,
)
from .seam_anchor_candidate_cli import (
    add_seam_anchor_candidate_subcommands,
    dispatch_seam_anchor_candidate_command,
)
from .seam_anchor_review_cli import (
    add_seam_anchor_review_subcommands,
    dispatch_seam_anchor_review_command,
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

    probe_parser = subparsers.add_parser(
        "probe-projected-scale",
        help="Report candidate-only target bone scales from two exact bundles",
    )
    probe_parser.add_argument("project_id", metavar="PROJECT")
    probe_parser.add_argument("--projected-motion-sha256", required=True)
    probe_parser.add_argument("--projected-bundle-sha256", required=True)
    probe_parser.add_argument("--motion-instance-sha256", required=True)
    probe_parser.add_argument("--motion-retarget-bundle-sha256", required=True)
    _state_root(probe_parser, state_root)
    add_p9_readonly_subcommands(subparsers, state_root)
    add_p9_policy_subcommands(subparsers, state_root)
    add_p9_v2_subcommands(subparsers, state_root)
    add_p9_bundle_subcommands(subparsers, state_root)
    add_p10_candidate_subcommands(subparsers, state_root)
    add_p10_decision_subcommands(subparsers)
    add_p10_probe_subcommands(subparsers, state_root)
    add_p10_preview_subcommands(subparsers, state_root)
    add_p10_runtime_capture_subcommands(subparsers, state_root)
    add_p10_visual_review_subcommands(subparsers, state_root)
    add_p10_review_admission_subcommands(subparsers, state_root)
    add_p10_amplitude_envelope_subcommands(subparsers, state_root)
    add_p10_continuous_proof_subcommands(subparsers, state_root)
    add_p10_dynamic_seam_subcommands(subparsers, state_root)
    add_p10_motion_consumer_admission_subcommands(subparsers, state_root)
    add_p10_motion_instance_v3_subcommands(subparsers, state_root)
    add_p10_spine42_v3_subcommands(subparsers, state_root)
    add_p10_spine42_v3_runtime_subcommands(subparsers, state_root)
    add_p10_spine42_v3_raster_review_subcommands(subparsers, state_root)
    add_seam_anchor_candidate_subcommands(subparsers, state_root)
    add_seam_anchor_review_subcommands(subparsers, state_root)


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
        elif command == "probe-projected-scale":
            result = probe_projected_scale(
                args.state_root,
                args.project_id,
                projected_motion_sha256=args.projected_motion_sha256,
                projected_bundle_sha256=args.projected_bundle_sha256,
                motion_instance_sha256=args.motion_instance_sha256,
                motion_retarget_bundle_sha256=(
                    args.motion_retarget_bundle_sha256
                ),
            )
        else:
            status = dispatch_p9_readonly_command(args)
            if status is not None:
                return status
            status = dispatch_p9_policy_command(args)
            if status is not None:
                return status
            status = dispatch_p9_v2_command(args)
            if status is not None:
                return status
            status = dispatch_p9_bundle_command(args)
            if status is not None:
                return status
            status = dispatch_p10_candidate_command(args)
            if status is not None:
                return status
            status = dispatch_p10_decision_command(args)
            if status is not None:
                return status
            status = dispatch_p10_probe_command(args)
            if status is not None:
                return status
            status = dispatch_p10_preview_command(args)
            if status is not None:
                return status
            status = dispatch_p10_runtime_capture_command(args)
            if status is not None:
                return status
            status = dispatch_p10_visual_review_command(args)
            if status is not None:
                return status
            status = dispatch_p10_review_admission_command(args)
            if status is not None:
                return status
            status = dispatch_p10_amplitude_envelope_command(args)
            if status is not None:
                return status
            status = dispatch_p10_continuous_proof_command(args)
            if status is not None:
                return status
            status = dispatch_p10_dynamic_seam_command(args)
            if status is not None:
                return status
            status = dispatch_p10_motion_consumer_admission_command(args)
            if status is not None:
                return status
            status = dispatch_p10_motion_instance_v3_command(args)
            if status is not None:
                return status
            status = dispatch_p10_spine42_v3_command(args)
            if status is not None:
                return status
            status = dispatch_p10_spine42_v3_runtime_command(args)
            if status is not None:
                return status
            status = dispatch_p10_spine42_v3_raster_review_command(args)
            if status is not None:
                return status
            status = dispatch_seam_anchor_candidate_command(args)
            return status if status is not None \
                else dispatch_seam_anchor_review_command(args)
    except ProjectedMotionCommandError as exc:
        _print({"ok": False, "status": "error", "error": str(exc)})
        return 2
    payload = _payload(result)
    payload.update(ok=True, status="passed")
    _print(payload)
    return 0


def _payload(result: Any) -> dict[str, Any]:
    values = asdict(result) if is_dataclass(result) else vars(result)
    return _jsonable(values)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _state_root(parser: argparse.ArgumentParser, default: Path) -> None:
    parser.add_argument("--state-root", type=Path, default=default)


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
