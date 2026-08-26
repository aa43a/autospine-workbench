"""Stable candidate identities shared by reviewed motion-policy decisions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .depth_order_candidate_validation import (
    depth_order_candidates_sha256,
    require_depth_order_candidates,
)
from .foot_lock_candidate_validation import (
    foot_lock_candidates_sha256,
    require_foot_lock_candidates,
)


FOOT_ID_DOMAIN = "autospine-motion-policy-foot-candidate-id/v1"
DEPTH_ID_DOMAIN = "autospine-motion-policy-depth-candidate-id/v1"


class MotionPolicyCandidateInventoryError(ValueError):
    """Raised when foot/depth reports do not share one immutable source chain."""


@dataclass(frozen=True, slots=True)
class MotionPolicyCandidate:
    """Minimal derived metadata; candidate metrics remain in source reports."""

    candidate_id: str
    kind: str
    tick: int
    foot_state: str | None = None
    depth_slots: tuple[str, str] | None = None
    depth_pair_id: str | None = None
    depth_event_index: int | None = None
    depth_to_front_slot: str | None = None


@dataclass(frozen=True, slots=True)
class MotionPolicyCandidateInventory:
    project_id: str
    clip_id: str
    foot_sha256: str
    depth_sha256: str
    loop: bool
    _source_json: str
    candidates: tuple[MotionPolicyCandidate, ...]
    unconstrained_foot_ticks: tuple[int, ...]

    @property
    def source(self) -> dict[str, Any]:
        return json.loads(self._source_json)


def derive_motion_policy_candidates(
    foot_candidates: Mapping[str, Any],
    depth_candidates: Mapping[str, Any],
) -> MotionPolicyCandidateInventory:
    """Validate two reports, cross-bind them, and derive stable candidate IDs."""

    try:
        require_foot_lock_candidates(foot_candidates)
        require_depth_order_candidates(depth_candidates)
        _cross_sources(foot_candidates, depth_candidates)
        foot_sha = foot_lock_candidates_sha256(foot_candidates)
        depth_sha = depth_order_candidates_sha256(depth_candidates)
        candidates = _foot_candidates(foot_candidates, foot_sha)
        candidates.extend(_depth_candidates(depth_candidates, depth_sha))
        candidates.sort(key=lambda row: row.candidate_id)
        if len({row.candidate_id for row in candidates}) != len(candidates):
            raise MotionPolicyCandidateInventoryError(
                "Motion-policy candidate identity collision"
            )
        depth_source = depth_candidates["source"]
        source = {
            "foot_lock_candidates_sha256": foot_sha,
            "depth_order_candidates_sha256": depth_sha,
            "depth_pair_policy_sha256": depth_source[
                "depth_pair_policy_sha256"
            ],
            "p8": json.loads(json.dumps(depth_source["p8"])),
            "p5": json.loads(json.dumps(depth_source["p5"])),
            "p3": json.loads(json.dumps(depth_source["p3"])),
        }
        return MotionPolicyCandidateInventory(
            project_id=str(foot_candidates["project_id"]),
            clip_id=str(foot_candidates["clip_id"]),
            foot_sha256=foot_sha,
            depth_sha256=depth_sha,
            loop=bool(depth_candidates["timing"]["loop"]),
            _source_json=_canonical(source),
            candidates=tuple(candidates),
            unconstrained_foot_ticks=tuple(
                row["tick"] for row in foot_candidates["samples"]
                if row["state"] == "unconstrained"
            ),
        )
    except MotionPolicyCandidateInventoryError:
        raise
    except (KeyError, OverflowError, TypeError, ValueError) as exc:
        raise MotionPolicyCandidateInventoryError(
            f"Motion-policy candidate inventory failed: {exc}"
        ) from exc


def _cross_sources(foot, depth) -> None:
    if foot["project_id"] != depth["project_id"] \
            or foot["clip_id"] != depth["clip_id"]:
        raise MotionPolicyCandidateInventoryError(
            "Motion-policy candidate project or clip differs"
        )
    left, right = foot["source"], depth["source"]
    comparisons = (
        (left["projected_motion_sha256"], right["p8"]["projected_motion_sha256"]),
        (left["projected_bundle_sha256"], right["p8"]["bundle_sha256"]),
        (left["camera_sha256"], right["p8"]["camera_sha256"]),
        (left["p7_motion_sha256"], right["p8"]["p7_motion_sha256"]),
        (left["p7_motion_sha256"], right["p8"]["legacy_motion_sha256"]),
        (left["p7_bundle_sha256"], right["p8"]["p7_bundle_sha256"]),
        (left["p7_run_sha256"], right["p8"]["p7_run_sha256"]),
        (left["target_profile_sha256"], right["p5"]["target_profile_sha256"]),
        (left["motion_instance_sha256"], right["p5"]["instance_sha256"]),
        (left["retarget_bundle_sha256"], right["p5"]["bundle_sha256"]),
        (left["retarget_run_document_sha256"], right["p5"]["run_sha256"]),
        (left["p3_rig_sha256"], right["p3"]["rig_sha256"]),
        (left["p3_bundle_sha256"], right["p3"]["bundle_sha256"]),
        (left["instance_motion_ir_sha256"], right["p8"]["p7_motion_sha256"]),
        (left["instance_motion_bundle_sha256"], right["p8"]["p7_bundle_sha256"]),
    )
    if any(first != second for first, second in comparisons):
        raise MotionPolicyCandidateInventoryError(
            "Motion-policy candidate P8/P5/P3 source chains differ"
        )
    foot_ticks = [row["tick"] for row in foot["samples"]]
    depth_ticks = [row["tick"] for row in depth["pairs"][0]["samples"]]
    if foot_ticks != depth_ticks:
        raise MotionPolicyCandidateInventoryError(
            "Motion-policy candidate frame schedules differ"
        )


def _foot_candidates(document, report_sha: str) -> list[MotionPolicyCandidate]:
    rows = []
    for sample in document["samples"]:
        if sample["state"] == "unconstrained":
            continue
        payload = {
            "report_sha256": report_sha,
            "source_frame_index": sample["source_frame_index"],
            "tick": sample["tick"],
        }
        rows.append(MotionPolicyCandidate(
            candidate_id=_candidate_id(FOOT_ID_DOMAIN, payload),
            kind="foot_lock",
            tick=sample["tick"],
            foot_state=sample["state"],
        ))
    return rows


def _depth_candidates(document, report_sha: str) -> list[MotionPolicyCandidate]:
    rows = []
    for pair in document["pairs"]:
        slots = tuple(row["slot_id"] for row in pair["slots"])
        for event_index, event in enumerate(pair["events"]):
            payload = {
                "report_sha256": report_sha,
                "pair_id": pair["pair_id"],
                "event_index": event_index,
                "source_frame_index": event["source_frame_index"],
                "tick": event["tick"],
                "from_front_slot": event["from_front_slot"],
                "to_front_slot": event["to_front_slot"],
            }
            rows.append(MotionPolicyCandidate(
                candidate_id=_candidate_id(DEPTH_ID_DOMAIN, payload),
                kind="depth_order",
                tick=event["tick"],
                depth_slots=(str(slots[0]), str(slots[1])),
                depth_pair_id=str(pair["pair_id"]),
                depth_event_index=event_index,
                depth_to_front_slot=str(event["to_front_slot"]),
            ))
    return rows


def _candidate_id(domain: str, payload: Mapping[str, Any]) -> str:
    digest = hashlib.sha256()
    for value in (domain.encode("ascii"), _canonical(payload).encode("utf-8")):
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)
    prefix = "foot" if domain == FOOT_ID_DOMAIN else "depth"
    return f"{prefix}-{digest.hexdigest()}"


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
