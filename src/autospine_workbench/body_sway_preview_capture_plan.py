"""Deterministic bounded still-frame plan for later official-runtime capture."""

from __future__ import annotations

from bisect import bisect_left
from fractions import Fraction
import json
from typing import Any

from .body_sway_preview_inputs import BodySwayPreviewInputs
from .body_sway_preview_profile import (
    BASE_ANIMATION_NAME,
    CAPTURE_PLAN_DIGEST_DOMAIN,
    COMBINED_ANIMATION_NAME,
)
from .body_sway_preview_projection import BodySwayPreviewProjection
from .body_sway_probe_math_inputs import (
    normalize_phases,
    require_cycles,
)
from .resolved_project import canonical_sha256
from .spine42_runtime_contract import (
    DEFAULT_BACKGROUND,
    DEFAULT_DPR,
    DEFAULT_VIEWPORT,
)


MAX_CAPTURE_CASES = 55


class BodySwayPreviewCapturePlanError(ValueError):
    """Raised when an exact projection cannot form the fixed capture plan."""


def build_body_sway_preview_capture_plan(
    inputs: BodySwayPreviewInputs,
    projection: BodySwayPreviewProjection,
) -> dict[str, Any]:
    """Select setup and paired base/combined frames without visual claims."""

    try:
        if type(inputs) is not BodySwayPreviewInputs \
                or type(projection) is not BodySwayPreviewProjection:
            raise BodySwayPreviewCapturePlanError(
                "Capture planning requires exact preview inputs and projection"
            )
        metadata = projection.public_metadata
        if metadata["projection_sha256"] != projection.sha256 \
                or metadata["probe_tick_schedule_sha256"] \
                != inputs.report["schedule"]["tick_schedule_sha256"]:
            raise BodySwayPreviewCapturePlanError(
                "Capture projection differs from exact P10.2 evidence"
            )
        ticks = select_body_sway_preview_capture_ticks(
            inputs.timing, inputs.selection, projection.sample_ticks
        )
        cases = [_case("setup", None, 0, inputs.timing)]
        for tick in ticks:
            cases.extend((
                _case(f"base-t{tick:09d}", BASE_ANIMATION_NAME,
                      tick, inputs.timing),
                _case(f"combined-t{tick:09d}", COMBINED_ANIMATION_NAME,
                      tick, inputs.timing),
            ))
        if len(cases) > MAX_CAPTURE_CASES:
            raise BodySwayPreviewCapturePlanError(
                "Body-sway capture case count exceeds the fixed profile"
            )
        canvas = inputs.probe_inputs.rig["canvas"]
        body = {
            "viewport": {
                "width": DEFAULT_VIEWPORT[0],
                "height": DEFAULT_VIEWPORT[1],
            },
            "device_pixel_ratio": DEFAULT_DPR,
            "background": DEFAULT_BACKGROUND,
            "preserve_drawing_buffer": True,
            "world_viewport": {
                "x": 0.0, "y": 0.0,
                "width": float(canvas["width"]),
                "height": float(canvas["height"]),
            },
            "selection_scope": "bounded-stills-for-manual-review",
            "cases": cases,
        }
        return {
            "capture_plan_sha256": canonical_sha256({
                "domain": CAPTURE_PLAN_DIGEST_DOMAIN, **body,
            }),
            **body,
        }
    except BodySwayPreviewCapturePlanError:
        raise
    except (
        KeyError, OverflowError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayPreviewCapturePlanError(
            f"Body-sway preview capture planning failed: {exc}"
        ) from exc


def body_sway_capture_plan_sha256(plan: dict[str, Any]) -> str:
    """Recompute the domain-separated identity of a detached plan."""

    body = json.loads(json.dumps(
        plan, allow_nan=False, sort_keys=True, separators=(",", ":")
    ))
    supplied = body.pop("capture_plan_sha256", None)
    result = canonical_sha256({
        "domain": CAPTURE_PLAN_DIGEST_DOMAIN, **body,
    })
    if supplied != result:
        raise BodySwayPreviewCapturePlanError(
            "Body-sway capture plan digest is inconsistent"
        )
    return result


def select_body_sway_preview_capture_ticks(
    timing: dict[str, Any],
    selection: dict[str, Any],
    schedule: tuple[int, ...],
) -> tuple[int, ...]:
    """Select exact schedule ticks for the fixed bounded still-frame plan."""

    duration = timing["duration_ticks"]
    parameters = selection["parameters"]
    cycles = require_cycles(parameters["cycles"])
    ideals = {Fraction(0), Fraction(duration)}
    ideals.update(Fraction(duration * index, 8) for index in range(9))
    for _bone_id, phase in normalize_phases(
        parameters["per_bone_phase_fraction"]
    ):
        first_quarter = _ceil(4 * phase)
        for offset in range(4):
            ideals.add(
                Fraction(duration, cycles)
                * (Fraction(first_quarter + offset, 4) - phase)
            )
    return tuple(sorted({_nearest(schedule, ideal) for ideal in ideals}))


def _nearest(schedule: tuple[int, ...], ideal: Fraction) -> int:
    index = bisect_left(schedule, ideal)
    if index == 0:
        return schedule[0]
    if index == len(schedule):
        return schedule[-1]
    lower, upper = schedule[index - 1], schedule[index]
    return lower if ideal - lower <= upper - ideal else upper


def _case(identifier, animation, tick, timing):
    return {
        "case_id": identifier,
        "animation": animation,
        "tick": tick,
        "time_seconds": tick / timing["ticks_per_second"],
    }


def _ceil(value: Fraction) -> int:
    return -(-value.numerator // value.denominator)
