"""Synthetic on-disk fixtures for automatic motion-policy package tests."""

from __future__ import annotations

import json
from pathlib import Path

from autospine_workbench.depth_order_candidate_validation import (
    depth_order_candidates_sha256,
)
from autospine_workbench.foot_lock_candidate_validation import (
    foot_lock_candidates_sha256,
)


def write_review_package(
    state_root: Path,
    policy: dict,
    foot: dict,
    depth: dict,
    *,
    motion_id: str = "motion-a",
    envelope_candidates: bool = True,
) -> Path:
    directory = state_root / "reviews" / motion_id / policy["project_id"]
    directory.mkdir(parents=True, exist_ok=True)
    _write(directory / "depth-pair-policy.json", policy)
    if envelope_candidates:
        foot_value = _envelope(
            foot, foot_lock_candidates_sha256(foot), "private-foot-source",
        )
        depth_value = _envelope(
            depth, depth_order_candidates_sha256(depth), "private-depth-source",
        )
    else:
        foot_value, depth_value = foot, depth
    _write(directory / "foot-lock-candidates.envelope.json", foot_value)
    _write(directory / "depth-order-candidates.envelope.json", depth_value)
    return directory


def _envelope(report: dict, sha256: str, private_path: str) -> dict:
    return {
        "input_bundle_paths": [f"C:/private-package-root/{private_path}"],
        "report_sha256": sha256,
        "report": report,
        "ok": True,
        "status": "passed",
    }


def _write(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(
            value, ensure_ascii=False, allow_nan=False, separators=(",", ":"),
        ),
        encoding="utf-8",
    )
