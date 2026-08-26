"""Compile review-only depth-order switch candidates from exact evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .depth_order_candidate_validation import (
    FORMAT,
    FORMAT_VERSION,
    DepthOrderCandidateValidationError,
    require_depth_order_candidates,
)
from .depth_order_inputs import (
    DepthOrderInputError,
    require_depth_order_inputs,
)
from .depth_order_schmitt import (
    DepthOrderSchmittError,
    evaluate_depth_pair,
    quantize_depth_score,
)
from .depth_pair_policy import (
    DepthPairPolicyError,
    depth_pair_policy_sha256,
    require_depth_pair_policy,
)
from .mesh_bundle_integrity import VerifiedMeshBundle
from .motion_retarget_bundle_integrity import VerifiedMotionRetargetBundle
from .projected_motion_bundle_integrity import VerifiedProjectedMotionBundle
from .resolved_project import canonical_sha256


GENERATOR_ID = "depth-pair-schmitt-candidate-generator"
GENERATOR_VERSION = "1.0.0"


class DepthOrderCandidateError(ValueError):
    """Raised when reviewed inputs cannot form depth-order candidates."""


@dataclass(frozen=True, slots=True)
class DepthOrderCandidates:
    """Frozen candidate-only evidence with isolated document access."""

    _canonical_json: str

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


def compile_depth_order_candidates(
    projected_bundle: VerifiedProjectedMotionBundle,
    retarget_bundle: VerifiedMotionRetargetBundle,
    mesh_bundle: VerifiedMeshBundle,
    policy: Mapping[str, Any],
) -> DepthOrderCandidates:
    """Compile pairwise candidates without changing animation or slot state."""

    try:
        inputs = require_depth_order_inputs(
            projected_bundle, retarget_bundle, mesh_bundle
        )
        require_depth_pair_policy(policy, inputs=inputs)
        document = _document(inputs, policy)
        require_depth_order_candidates(
            document, policy=policy, inputs=inputs
        )
        encoded = json.dumps(
            document, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        )
        result = DepthOrderCandidates(encoded)
        if result.sha256 != canonical_sha256(result.document):
            raise DepthOrderCandidateError(
                "Depth-order candidate identity is inconsistent"
            )
        return result
    except DepthOrderCandidateError:
        raise
    except (
        DepthOrderCandidateValidationError,
        DepthOrderInputError,
        DepthOrderSchmittError,
        DepthPairPolicyError,
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
    ) as exc:
        raise DepthOrderCandidateError(
            f"Depth-order candidate compilation failed: {exc}"
        ) from exc


def _document(inputs, policy):
    projected = inputs.projected
    sign = 1.0 if inputs.camera["depth_positive"] == "toward_camera" else -1.0
    tracks = {row["role"]: row for row in projected["segment_tracks"]}
    pairs = [_pair(row, tracks, sign, policy["hysteresis"])
             for row in policy["pairs"]]
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "project_id": policy["project_id"],
        "clip_id": policy["clip_id"],
        "source": {
            **inputs.identities,
            "depth_pair_policy_sha256": depth_pair_policy_sha256(policy),
        },
        "timing": dict(projected["timing"]),
        "projection": {
            "camera_depth_positive": inputs.camera["depth_positive"],
            "front_score_sign": int(sign),
        },
        "generator": {
            "id": GENERATOR_ID,
            "version": GENERATOR_VERSION,
            "numeric_precision_decimals": 9,
        },
        "semantics": {
            "mode": "candidate_only",
            "apply_policy": "review_required",
            "decision_emitted": False,
            "proxy_quality": "bone-segment-midpoint",
            "raster_truth_claimed": False,
            "runtime_timeline_emitted": False,
            "motion_instance_mutated": False,
            "spine_draw_order_emitted": False,
            "evidence_window": "inclusive_source_frame_range",
        },
        "hysteresis": dict(policy["hysteresis"]),
        "summary": {
            "status": "candidate_only",
            "pair_count": len(pairs),
            "sample_count": sum(len(row["samples"]) for row in pairs),
            "event_count": sum(len(row["events"]) for row in pairs),
            "collapsed_sample_count": 0,
        },
        "pairs": pairs,
    }


def _pair(pair, tracks, sign, hysteresis):
    slots = pair["slots"]
    track_by_slot = {
        row["slot_id"]: tracks[row["depth_role"]] for row in slots
    }
    first_track = track_by_slot[slots[0]["slot_id"]]
    score_rows = []
    samples = []
    for index, frame in enumerate(first_track["samples"]):
        scores = []
        score_map = {}
        for slot in slots:
            sample = track_by_slot[slot["slot_id"]]["samples"][index]
            if sample["projection_state"] != "observable":
                raise DepthOrderCandidateError(
                    f"Depth role is collapsed: {slot['depth_role']}"
                )
            midpoint = sample["midpoint_depth_root_relative_normalized"]
            score = quantize_depth_score(float(midpoint) * sign)
            scores.append({
                "slot_id": slot["slot_id"],
                "depth_role": slot["depth_role"],
                "midpoint_depth_root_relative_normalized": midpoint,
                "front_score": score,
            })
            score_map[slot["slot_id"]] = score
        score_rows.append({
            "source_frame_index": frame["source_frame_index"],
            "tick": frame["tick"],
            "scores": score_map,
        })
        samples.append({
            "source_frame_index": frame["source_frame_index"],
            "tick": frame["tick"],
            "scores": scores,
            "score_delta_first_minus_second": quantize_depth_score(
                scores[0]["front_score"] - scores[1]["front_score"]
            ),
        })
    states, events = evaluate_depth_pair(
        score_rows,
        slot_ids=(slots[0]["slot_id"], slots[1]["slot_id"]),
        setup_front_slot=pair["setup_front_slot"],
        enter_threshold=float(hysteresis["enter_threshold"]),
        exit_threshold=float(hysteresis["exit_threshold"]),
        minimum_hold_frames=hysteresis["minimum_hold_frames"],
    )
    for sample, state in zip(samples, states):
        sample.update(state)
    return {
        "pair_id": pair["pair_id"],
        "slots": [dict(row) for row in slots],
        "setup_front_slot": pair["setup_front_slot"],
        "samples": samples,
        "events": events,
    }
