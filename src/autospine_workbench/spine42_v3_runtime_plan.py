"""Pure bounded capture planning from one exact verified Spine v3 bundle."""
from __future__ import annotations

from collections.abc import Mapping
from fractions import Fraction
import json
import math
from typing import Any

from .resolved_project import canonical_sha256
from .spine42_v3_bundle_integrity import VerifiedSpine42V3Bundle
from .spine42_v3_bundle_integrity import replay_verified_spine42_v3_bundle
from .spine42_v3_runtime_profile import (
    MAX_CAPTURE_ARTIFACTS,
    MAX_COMPOSITE_CASES,
    MAX_SETUP_ATTACHMENTS,
    PLAN_HASH_DOMAIN,
    TICKS_PER_SECOND,
    spine42_v3_runtime_profile,
    spine42_v3_runtime_profile_sha256,
)


PLAN_FORMAT = "autospine-spine42-v3-runtime-raster-plan"
PLAN_VERSION = 1
class Spine42V3RuntimePlanError(ValueError):
    """Raised when an exact bundle cannot form the bounded capture plan."""


def build_spine42_v3_runtime_plan(
    bundle: VerifiedSpine42V3Bundle,
) -> dict[str, Any]:
    """Derive setup, fixed, extrema, boundary, and loop-neighbor stills."""

    try:
        if type(bundle) is not VerifiedSpine42V3Bundle:
            raise Spine42V3RuntimePlanError(
                "Runtime planning requires an exact verified Spine v3 bundle"
            )
        replay_verified_spine42_v3_bundle(bundle)
        skeleton = bundle.skeleton_json
        animation = skeleton["animations"][bundle.clip_id]
        duration, duration_seconds, samples = _selected_samples(animation)
        attachments = _setup_attachments(skeleton)
        if len(attachments) > MAX_SETUP_ATTACHMENTS:
            raise Spine42V3RuntimePlanError(
                "Active setup attachment count exceeds the fixed profile"
            )
        cases = [_capture_case(
            0, "setup", None, 0, 0.0, ("setup",)
        )]
        for ordinal, (tick, time_seconds, reasons) in enumerate(
            samples, start=1
        ):
            cases.append(_capture_case(
                ordinal, f"motion-t{tick:09d}", bundle.clip_id, tick,
                time_seconds, tuple(sorted(reasons)),
            ))
        if len(cases) > MAX_COMPOSITE_CASES:
            raise Spine42V3RuntimePlanError(
                "Composite case count exceeds the fixed profile; no cases were truncated"
            )
        artifacts = _artifacts(cases, attachments)
        if len(artifacts) > MAX_CAPTURE_ARTIFACTS:
            raise Spine42V3RuntimePlanError(
                "Capture artifact count exceeds the fixed profile"
            )
        profile = spine42_v3_runtime_profile()
        world = skeleton["skeleton"]
        body = {
            "format": PLAN_FORMAT,
            "format_version": PLAN_VERSION,
            "profile_sha256": spine42_v3_runtime_profile_sha256(),
            "source": {
                "project_id": bundle.project_id,
                "clip_id": bundle.clip_id,
                "skeleton_json_sha256": bundle.skeleton_json_sha256,
                "bundle_sha256": bundle.bundle_sha256,
            },
            "runtime": profile["runtime"],
            "harness": profile["harness"],
            "browser_execution": profile["browser_execution"],
            "capture": {
                **profile["capture"],
                "world_viewport": {
                    key: float(world[key])
                    for key in ("x", "y", "width", "height")
                },
            },
            "sampled_scope": {
                "kind": "bounded-discrete-samples-only",
                "animation": bundle.clip_id,
                "duration_ticks": duration,
                "duration_seconds": duration_seconds,
                "sampled_ticks": [row[0] for row in samples],
                "sampled_time_seconds": [row[1] for row in samples],
                "sampled_tick_ranges": [[row[0], row[0]] for row in samples],
                "max_tick_quantization_error_seconds": max(
                    abs(time - tick / TICKS_PER_SECOND)
                    for tick, time, _reasons in samples
                ),
                "continuous_time_safety_claimed": False,
                "unsampled_ticks_covered": False,
            },
            "attachments": attachments,
            "cases": cases,
            "artifacts": artifacts,
        }
        return {
            **body,
            "capture_plan_sha256": canonical_sha256({
                "domain": PLAN_HASH_DOMAIN, **body,
            }),
        }
    except Spine42V3RuntimePlanError:
        raise
    except (
        AttributeError, KeyError, OverflowError, TypeError,
        UnicodeError, ValueError,
    ) as exc:
        raise Spine42V3RuntimePlanError(
            f"Spine v3 runtime capture planning failed: {exc}"
        ) from exc


def spine42_v3_runtime_plan_sha256(plan: Mapping[str, Any]) -> str:
    """Recompute and require the domain-separated plan identity."""

    try:
        body = json.loads(canonical_spine42_v3_runtime_plan_bytes(plan))
        supplied = body.pop("capture_plan_sha256", None)
        result = canonical_sha256({"domain": PLAN_HASH_DOMAIN, **body})
        if supplied != result:
            raise Spine42V3RuntimePlanError(
                "Runtime capture plan digest is inconsistent"
            )
        return result
    except Spine42V3RuntimePlanError:
        raise
    except (AttributeError, TypeError, ValueError) as exc:
        raise Spine42V3RuntimePlanError(
            "Runtime capture plan cannot be hashed"
        ) from exc


def canonical_spine42_v3_runtime_plan_bytes(
    value: Mapping[str, Any],
) -> bytes:
    """Serialize a plan-shaped mapping as stable strict JSON bytes."""

    if not isinstance(value, Mapping):
        raise Spine42V3RuntimePlanError("Runtime capture plan must be an object")
    try:
        return json.dumps(
            dict(value), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    except (OverflowError, TypeError, UnicodeError, ValueError) as exc:
        raise Spine42V3RuntimePlanError(
            "Runtime capture plan is not strict finite JSON"
        ) from exc


def _selected_samples(animation: Mapping[str, Any]):
    tracks = animation["bones"]
    duration_seconds = max(
        _time(frames[-1]["time"])
        for timelines in tracks.values() for frames in timelines.values()
    )
    reasons: dict[float, set[str]] = {}
    for index in range(9):
        time = duration_seconds * index / 8
        _reason(reasons, time, "fixed-duration-fraction")
    for timelines in tracks.values():
        for name, frames in timelines.items():
            channels = ("value",) if name == "rotate" else ("x", "y")
            for channel in channels:
                _add_extrema(reasons, frames, channel)
    for frame in animation.get("events", []):
        _reason(reasons, _time(frame["time"]), "event-boundary")
    for frame in animation["drawOrder"]:
        _reason(reasons, _time(frame["time"]), "draw-order-boundary")
    quantum = 1 / TICKS_PER_SECOND
    for time in (
        0.0, min(quantum, duration_seconds),
        max(0.0, duration_seconds - quantum), duration_seconds,
    ):
        _reason(reasons, time, "loop-endpoint-neighbor")
    samples, observed_ticks = [], set()
    for time in sorted(reasons):
        tick = _tick(time)
        if tick in observed_ticks:
            raise Spine42V3RuntimePlanError(
                "Distinct sample times collide on the pinned capture tick grid"
            )
        observed_ticks.add(tick)
        samples.append((tick, time, reasons[time]))
    return _tick(duration_seconds), duration_seconds, samples


def _add_extrema(reasons, frames, channel) -> None:
    values = [float(frame[channel]) for frame in frames]
    for index in range(1, len(frames) - 1):
        before, current, after = values[index - 1:index + 2]
        if (current >= before and current >= after and
                (current > before or current > after)) or (
                current <= before and current <= after and
                (current < before or current < after)):
            _reason(reasons, _time(frames[index]["time"]), "track-local-extremum")
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
            raise Spine42V3RuntimePlanError(
                "Setup attachment is absent from the default skin"
            )
        result.append({
            "ordinal": len(result), "slot_id": slot["name"],
            "attachment_id": attachment,
        })
    return result


def _capture_case(
    ordinal, identifier, animation, tick, time_seconds=None, reasons=(),
):
    if time_seconds is None:
        time_seconds = tick / TICKS_PER_SECOND
    return {
        "case_id": identifier, "ordinal": ordinal,
        "animation": animation, "tick": tick,
        "time_seconds": time_seconds,
        "selection_reasons": list(reasons),
        "artifact_ids": [],
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
        raise Spine42V3RuntimePlanError("Timeline time is invalid")
    return float(value)


def _tick(value: Any) -> int:
    time = _time(value)
    scaled = Fraction(str(time)) * TICKS_PER_SECOND
    return (2 * scaled.numerator + scaled.denominator) // (2 * scaled.denominator)


def _reason(rows, tick, reason) -> None:
    rows.setdefault(tick, set()).add(reason)


__all__ = [
    "PLAN_FORMAT", "PLAN_VERSION", "Spine42V3RuntimePlanError",
    "build_spine42_v3_runtime_plan",
    "canonical_spine42_v3_runtime_plan_bytes",
    "spine42_v3_runtime_plan_sha256",
]
