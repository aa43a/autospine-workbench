"""Version-neutral bounded runtime capture case derivation."""

from __future__ import annotations

from collections.abc import Mapping
from fractions import Fraction
import math
from typing import Any


class RuntimeCapturePlanSemanticsError(ValueError):
    """Raised when skeleton semantics exceed a caller's fixed bounds."""


def derive_runtime_capture_plan_semantics(
    skeleton: Mapping[str, Any],
    clip_id: str,
    *,
    ticks_per_second: int,
    max_composite_cases: int,
    max_setup_attachments: int,
    max_capture_artifacts: int,
) -> dict[str, Any]:
    """Derive capture scope without source, version, profile, or hash identity."""

    animation = skeleton["animations"][clip_id]
    duration, duration_seconds, samples = _selected_samples(
        animation, ticks_per_second,
    )
    attachments = _setup_attachments(skeleton)
    if len(attachments) > max_setup_attachments:
        raise RuntimeCapturePlanSemanticsError(
            "Active setup attachment count exceeds the fixed profile"
        )
    cases = [_capture_case(0, "setup", None, 0, 0.0, ("setup",))]
    for ordinal, (tick, time_seconds, reasons) in enumerate(samples, start=1):
        cases.append(_capture_case(
            ordinal, f"motion-t{tick:09d}", clip_id, tick,
            time_seconds, tuple(sorted(reasons)),
        ))
    if len(cases) > max_composite_cases:
        raise RuntimeCapturePlanSemanticsError(
            "Composite case count exceeds the fixed profile; "
            "no cases were truncated"
        )
    artifacts = _artifacts(cases, attachments)
    if len(artifacts) > max_capture_artifacts:
        raise RuntimeCapturePlanSemanticsError(
            "Capture artifact count exceeds the fixed profile"
        )
    world = skeleton["skeleton"]
    return {
        "world_viewport": {
            key: float(world[key]) for key in ("x", "y", "width", "height")
        },
        "sampled_scope": {
            "kind": "bounded-discrete-samples-only",
            "animation": clip_id,
            "duration_ticks": duration,
            "duration_seconds": duration_seconds,
            "sampled_ticks": [row[0] for row in samples],
            "sampled_time_seconds": [row[1] for row in samples],
            "sampled_tick_ranges": [[row[0], row[0]] for row in samples],
            "max_tick_quantization_error_seconds": max(
                abs(time - tick / ticks_per_second)
                for tick, time, _reasons in samples
            ),
            "continuous_time_safety_claimed": False,
            "unsampled_ticks_covered": False,
        },
        "attachments": attachments,
        "cases": cases,
        "artifacts": artifacts,
    }


def _selected_samples(animation: Mapping[str, Any], ticks_per_second: int):
    tracks = animation["bones"]
    duration_seconds = max(
        _time(frames[-1]["time"])
        for timelines in tracks.values() for frames in timelines.values()
    )
    reasons: dict[float, set[str]] = {}
    for index in range(9):
        _reason(reasons, duration_seconds * index / 8,
                "fixed-duration-fraction")
    for timelines in tracks.values():
        for name, frames in timelines.items():
            channels = ("value",) if name == "rotate" else ("x", "y")
            for channel in channels:
                _add_extrema(reasons, frames, channel)
    for frame in animation.get("events", []):
        _reason(reasons, _time(frame["time"]), "event-boundary")
    for frame in animation["drawOrder"]:
        _reason(reasons, _time(frame["time"]), "draw-order-boundary")
    quantum = 1 / ticks_per_second
    for time in (
        0.0, min(quantum, duration_seconds),
        max(0.0, duration_seconds - quantum), duration_seconds,
    ):
        _reason(reasons, time, "loop-endpoint-neighbor")
    samples, observed_ticks = [], set()
    for time in sorted(reasons):
        tick = _tick(time, ticks_per_second)
        if tick in observed_ticks:
            raise RuntimeCapturePlanSemanticsError(
                "Distinct sample times collide on the pinned capture tick grid"
            )
        observed_ticks.add(tick)
        samples.append((tick, time, reasons[time]))
    return _tick(duration_seconds, ticks_per_second), duration_seconds, samples


def _add_extrema(reasons, frames, channel) -> None:
    values = [float(frame[channel]) for frame in frames]
    for index in range(1, len(frames) - 1):
        before, current, after = values[index - 1:index + 2]
        if (current >= before and current >= after and
                (current > before or current > after)) or (
                current <= before and current <= after and
                (current < before or current < after)):
            _reason(reasons, _time(frames[index]["time"]),
                    "track-local-extremum")
    low, high = min(values), max(values)
    for frame, value in zip(frames, values, strict=True):
        if value == low or value == high:
            _reason(reasons, _time(frame["time"]), "track-global-extremum")


def _setup_attachments(skeleton: Mapping[str, Any]) -> list[dict[str, Any]]:
    default = skeleton["skins"][0]["attachments"]
    result = []
    for slot in skeleton["slots"]:
        attachment = slot.get("attachment")
        if attachment is None:
            continue
        if attachment not in default.get(slot["name"], {}):
            raise RuntimeCapturePlanSemanticsError(
                "Setup attachment is absent from the default skin"
            )
        result.append({
            "ordinal": len(result), "slot_id": slot["name"],
            "attachment_id": attachment,
        })
    return result


def _capture_case(ordinal, identifier, animation, tick, time_seconds, reasons):
    return {
        "case_id": identifier, "ordinal": ordinal,
        "animation": animation, "tick": tick,
        "time_seconds": time_seconds,
        "selection_reasons": list(reasons), "artifact_ids": [],
    }


def _artifacts(cases, attachments):
    result = []
    for case in cases:
        prefix = f"case-{case['ordinal']:03d}"
        rows = [
            _artifact(prefix, "opaque", "opaque_composite", case, None, None),
            _artifact(prefix, "alpha", "transparent_composite", case, None, None),
        ]
        for attachment in attachments:
            rows.append(_artifact(
                prefix, f"isolate-{attachment['ordinal']:02d}",
                "attachment_isolate", case,
                attachment["slot_id"], attachment["attachment_id"],
            ))
        case["artifact_ids"] = [row["artifact_id"] for row in rows]
        result.extend(rows)
    return result


def _artifact(prefix, suffix, kind, case, slot, attachment):
    artifact_id = f"{prefix}.{suffix}"
    background = "#20242aff" if kind == "opaque_composite" else "#00000000"
    return {
        "artifact_id": artifact_id, "path": f"{artifact_id}.png",
        "kind": kind, "case_id": case["case_id"],
        "slot_id": slot, "attachment_id": attachment,
        "background": background,
    }


def _time(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(float(value)) or float(value) < 0:
        raise RuntimeCapturePlanSemanticsError("Timeline time is invalid")
    return float(value)


def _tick(value: Any, ticks_per_second: int) -> int:
    time = _time(value)
    scaled = Fraction(str(time)) * ticks_per_second
    return (2 * scaled.numerator + scaled.denominator) // (2 * scaled.denominator)


def _reason(rows, time, reason) -> None:
    rows.setdefault(time, set()).add(reason)


__all__ = [
    "RuntimeCapturePlanSemanticsError",
    "derive_runtime_capture_plan_semantics",
]
