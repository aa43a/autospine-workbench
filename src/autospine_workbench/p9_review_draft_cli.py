"""CLI boundary for preparing a non-authoritative P9 review draft."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from .p9_review_draft import P9ReviewDraftError, prepare_p9_review_draft


COMMAND = "prepare-motion-policy-review-draft"


def add_p9_review_draft_subcommand(
    subparsers: Any, state_root: Path,
) -> None:
    parser = subparsers.add_parser(
        COMMAND,
        help="Prepare Foot evidence and a pending depth proposal only",
    )
    parser.add_argument("project_id", metavar="PROJECT")
    parser.add_argument("motion_namespace", metavar="NEW_NAMESPACE")
    for field in (
        "p3-rig-sha256", "p3-bundle-sha256",
        "p4-profile-sha256", "p4-bundle-sha256",
        "motion-instance-sha256", "motion-retarget-bundle-sha256",
        "p7-motion-sha256", "p7-bundle-sha256",
        "p8-motion-sha256", "p8-bundle-sha256",
    ):
        parser.add_argument(f"--{field}", required=True)
    parser.add_argument("--first-slot-id", required=True)
    parser.add_argument("--second-slot-id", required=True)
    parser.add_argument("--pair-id", required=True)
    parser.add_argument(
        "--max-correction-reference-ratio", type=float, default=0.25
    )
    parser.add_argument("--max-residual-px", type=float, default=8.0)
    parser.add_argument("--state-root", type=Path, default=state_root)


def dispatch_p9_review_draft_command(
    args: argparse.Namespace,
) -> int | None:
    if getattr(args, "command", None) != COMMAND:
        return None
    try:
        result = prepare_p9_review_draft(
            args.state_root, args.project_id, args.motion_namespace,
            p3_rig_sha256=args.p3_rig_sha256,
            p3_bundle_sha256=args.p3_bundle_sha256,
            p4_profile_sha256=args.p4_profile_sha256,
            p4_bundle_sha256=args.p4_bundle_sha256,
            motion_instance_sha256=args.motion_instance_sha256,
            motion_retarget_bundle_sha256=(
                args.motion_retarget_bundle_sha256
            ),
            p7_motion_sha256=args.p7_motion_sha256,
            p7_bundle_sha256=args.p7_bundle_sha256,
            p8_motion_sha256=args.p8_motion_sha256,
            p8_bundle_sha256=args.p8_bundle_sha256,
            first_slot_id=args.first_slot_id,
            second_slot_id=args.second_slot_id,
            pair_id=args.pair_id,
            max_correction_reference_ratio=(
                args.max_correction_reference_ratio
            ),
            max_residual_px=args.max_residual_px,
        )
    except P9ReviewDraftError as exc:
        _print({"ok": False, "status": "error", "error": str(exc)})
        return 2
    payload = _jsonable(asdict(result))
    payload.update({
        "ok": True,
        "status": "pending_human_depth_policy_review",
        "approved_depth_policy": False,
        "depth_candidates_emitted": False,
        "p9_adoption_emitted": False,
    })
    _print(payload)
    return 0


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))
