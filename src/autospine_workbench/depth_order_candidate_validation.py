"""Strict invariants for candidate-only depth-order evidence."""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
import re
from typing import Any

from .depth_order_candidate_evidence import validate_candidate_pairs
from .depth_order_inputs import DepthOrderInputs
from .depth_pair_policy import (
    HYSTERESIS_UNIT,
    depth_pair_policy_sha256,
    require_depth_pair_policy,
)
from .resolved_project import canonical_sha256
from .exact_json_contract import exact_json_equal


FORMAT = "autospine-depth-order-candidates"
FORMAT_VERSION = 1
MAX_DOCUMENT_BYTES = 64 * 1024 * 1024
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_FIELDS = {
    "p8": {
        "projected_motion_sha256", "bundle_sha256", "camera_sha256",
        "run_sha256", "legacy_motion_sha256", "p7_motion_sha256",
        "p7_bundle_sha256", "p7_run_sha256",
    },
    "p5": {
        "target_profile_sha256", "instance_sha256", "run_sha256",
        "retarget_report_sha256", "mesh_regression_sha256", "bundle_sha256",
    },
    "p3": {
        "base_rig_sha256", "base_bundle_sha256", "layer_manifest_sha256",
        "resolved_project_sha256", "rig_sha256", "run_sha256",
        "probes_sha256", "visuals_sha256", "bundle_sha256",
    },
}
_TOP = {
    "format", "format_version", "project_id", "clip_id", "source",
    "timing", "projection", "generator", "semantics", "hysteresis",
    "summary", "pairs",
}
_SEMANTICS = {
    "mode": "candidate_only",
    "apply_policy": "review_required",
    "decision_emitted": False,
    "proxy_quality": "bone-segment-midpoint",
    "raster_truth_claimed": False,
    "runtime_timeline_emitted": False,
    "motion_instance_mutated": False,
    "spine_draw_order_emitted": False,
    "evidence_window": "inclusive_source_frame_range",
}
class DepthOrderCandidateValidationError(ValueError):
    """Raised when depth-order candidate evidence is inconsistent or stale."""


def require_depth_order_candidates(
    document: Mapping[str, Any], *,
    policy: Mapping[str, Any] | None = None,
    inputs: DepthOrderInputs | None = None,
) -> None:
    """Validate standalone evidence and optional exact policy/source binding."""

    try:
        root = _object(document, "Depth-order candidates")
        _exact(root, _TOP, "Depth-order candidates")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root.get("format_version") != FORMAT_VERSION:
            raise DepthOrderCandidateValidationError(
                "Depth-order candidate format is unsupported"
            )
        _identifier(root.get("project_id"), "project_id")
        _identifier(root.get("clip_id"), "clip_id")
        _source(root.get("source"))
        frames = _timing(root.get("timing"))
        sign = _projection(root.get("projection"))
        _generator(root.get("generator"))
        if not exact_json_equal(root.get("semantics"), _SEMANTICS):
            raise DepthOrderCandidateValidationError(
                "Depth-order candidate semantics are unsupported"
            )
        hysteresis = _hysteresis(root.get("hysteresis"))
        counts = validate_candidate_pairs(
            root.get("pairs"), frames, sign, hysteresis
        )
        _summary(root.get("summary"), counts)
        if policy is not None or inputs is not None:
            if policy is None or inputs is None:
                raise DepthOrderCandidateValidationError(
                    "Exact candidate binding requires policy and inputs"
                )
            _cross(root, policy, inputs)
        encoded = json.dumps(
            dict(root), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise DepthOrderCandidateValidationError(
                "Depth-order candidate byte limit exceeded"
            )
    except DepthOrderCandidateValidationError:
        raise
    except (KeyError, OverflowError, TypeError, ValueError) as exc:
        raise DepthOrderCandidateValidationError(
            f"Depth-order candidate validation failed: {exc}"
        ) from exc

def depth_order_candidates_sha256(document: Mapping[str, Any]) -> str:
    require_depth_order_candidates(document)
    return canonical_sha256(document)

def _source(value):
    source = _object(value, "Depth-order candidate source")
    _exact(source, {"p8", "p5", "p3", "depth_pair_policy_sha256"},
           "Depth-order candidate source")
    policy_sha = source.get("depth_pair_policy_sha256")
    if not isinstance(policy_sha, str) or not _SHA.fullmatch(policy_sha):
        raise DepthOrderCandidateValidationError(
            "Depth-order policy SHA-256 is invalid"
        )
    for stage, fields in _SOURCE_FIELDS.items():
        row = _object(source.get(stage), f"Depth-order {stage} source")
        if set(row) != fields or any(
            not isinstance(item, str) or not _SHA.fullmatch(item)
            for item in row.values()
        ):
            raise DepthOrderCandidateValidationError(
                f"Depth-order {stage} source SHA inventory is invalid"
            )

def _timing(value):
    row = _object(value, "Depth-order timing")
    _exact(row, {"ticks_per_second", "duration_ticks", "loop", "frame_count"},
           "Depth-order timing")
    count = row.get("frame_count")
    duration = row.get("duration_ticks")
    if type(row.get("ticks_per_second")) is not int \
            or row["ticks_per_second"] != 1_000_000 \
            or type(count) is not int or not 2 <= count <= 4096 \
            or type(duration) is not int or not 1 <= duration <= 600_000_000 \
            or type(row.get("loop")) is not bool:
        raise DepthOrderCandidateValidationError(
            "Depth-order timing is invalid"
        )
    return count, duration

def _projection(value):
    row = _object(value, "Depth-order projection")
    _exact(row, {"camera_depth_positive", "front_score_sign"},
           "Depth-order projection")
    expected = {
        "toward_camera": 1, "away_from_camera": -1,
    }.get(row.get("camera_depth_positive"))
    if expected is None or type(row.get("front_score_sign")) is not int \
            or row["front_score_sign"] != expected:
        raise DepthOrderCandidateValidationError(
            "Depth-order front-score direction is invalid"
        )
    return expected

def _generator(value):
    from .depth_order_candidates import GENERATOR_ID, GENERATOR_VERSION
    expected = {
        "id": GENERATOR_ID, "version": GENERATOR_VERSION,
        "numeric_precision_decimals": 9,
    }
    if not exact_json_equal(value, expected):
        raise DepthOrderCandidateValidationError(
            "Depth-order candidate generator is unsupported"
        )

def _hysteresis(value):
    row = _object(value, "Depth-order hysteresis")
    _exact(row, {
        "unit", "enter_threshold", "exit_threshold", "minimum_hold_frames",
    },
           "Depth-order hysteresis")
    if row.get("unit") != HYSTERESIS_UNIT:
        raise DepthOrderCandidateValidationError(
            "Depth-order hysteresis unit is unsupported"
        )
    enter = _number(row.get("enter_threshold"), "enter threshold")
    exit_ = _number(row.get("exit_threshold"), "exit threshold")
    hold = row.get("minimum_hold_frames")
    if not enter > exit_ >= 0 or type(hold) is not int or not 1 <= hold <= 4096:
        raise DepthOrderCandidateValidationError(
            "Depth-order hysteresis is invalid"
        )
    return enter, exit_, hold

def _summary(value, counts):
    expected = {
        "status": "candidate_only", "pair_count": counts[0],
        "sample_count": counts[1], "event_count": counts[2],
        "collapsed_sample_count": 0,
    }
    if not exact_json_equal(value, expected):
        raise DepthOrderCandidateValidationError(
            "Depth-order summary differs from its evidence"
        )


def _cross(root, policy, inputs):
    if type(inputs) is not DepthOrderInputs:
        raise DepthOrderCandidateValidationError(
            "Depth-order exact inputs are invalid"
        )
    require_depth_pair_policy(policy, inputs=inputs)
    expected_source = {
        **inputs.identities,
        "depth_pair_policy_sha256": depth_pair_policy_sha256(policy),
    }
    if root["source"] != expected_source \
            or root["project_id"] != policy["project_id"] \
            or root["clip_id"] != policy["clip_id"] \
            or root["timing"] != inputs.projected["timing"] \
            or not exact_json_equal(
                root["hysteresis"], policy["hysteresis"]
            ):
        raise DepthOrderCandidateValidationError(
            "Depth-order source or policy binding is stale"
        )
    if [(row["pair_id"], row["slots"], row["setup_front_slot"])
            for row in root["pairs"]] != [
        (row["pair_id"], row["slots"], row["setup_front_slot"])
        for row in policy["pairs"]
    ]:
        raise DepthOrderCandidateValidationError(
            "Depth-order pair inventory differs from reviewed policy"
        )
    tracks = {row["role"]: row for row in inputs.projected["segment_tracks"]}
    for pair in root["pairs"]:
        for slot in pair["slots"]:
            upstream = tracks[slot["depth_role"]]["samples"]
            candidate_schedule = _schedule(pair["samples"])
            upstream_schedule = _schedule(upstream)
            if not exact_json_equal(candidate_schedule, upstream_schedule):
                raise DepthOrderCandidateValidationError(
                    "Depth-order frame schedule differs from P8"
                )
            for sample, source_sample in zip(pair["samples"], upstream):
                score = next(row for row in sample["scores"]
                             if row["slot_id"] == slot["slot_id"])
                if source_sample["projection_state"] != "observable" \
                        or not exact_json_equal(
                            score["midpoint_depth_root_relative_normalized"],
                            source_sample[
                                "midpoint_depth_root_relative_normalized"
                            ],
                        ):
                    raise DepthOrderCandidateValidationError(
                        "Depth-order midpoint evidence differs from P8"
                    )


def _schedule(rows):
    return [(row["source_frame_index"], row["tick"]) for row in rows]


def _number(value, label, *, absolute=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) \
            or (absolute and abs(float(value)) > 1024) \
            or (not absolute and not 0 <= float(value) <= 1024):
        raise DepthOrderCandidateValidationError(
            f"Depth-order {label} is invalid"
        )
    return float(value)


def _identifier(value, label):
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise DepthOrderCandidateValidationError(
            f"Depth-order {label} is invalid"
        )
    return value


def _object(value, label):
    if not isinstance(value, Mapping):
        raise DepthOrderCandidateValidationError(f"{label} must be an object")
    return value


def _array(value, label):
    if not isinstance(value, list):
        raise DepthOrderCandidateValidationError(f"{label} must be an array")
    return value


def _exact(value, fields, label):
    if set(value) != fields:
        raise DepthOrderCandidateValidationError(f"{label} fields are unsupported")
