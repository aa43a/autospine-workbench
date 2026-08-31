"""Deterministic 640px still plan using approved P10.2b world framing."""

from __future__ import annotations

import json
from typing import Any

from .body_sway_preview_capture_plan import (
    MAX_CAPTURE_CASES,
    select_body_sway_preview_capture_ticks,
)
from .body_sway_preview_inputs_v2 import BodySwayPreviewInputsV2
from .body_sway_preview_profile_v2 import (
    BASE_ANIMATION_NAME,
    CAPTURE_DEVICE_PIXEL_RATIO,
    CAPTURE_PLAN_DIGEST_DOMAIN,
    CAPTURE_VIEWPORT,
    COMBINED_ANIMATION_NAME,
)
from .body_sway_preview_projection_v2 import BodySwayPreviewProjectionV2
from .resolved_project import canonical_sha256
from .spine42_runtime_contract import DEFAULT_BACKGROUND


class BodySwayPreviewCapturePlanV2Error(ValueError):
    """Raised when exact v2 projection and reviewed framing disagree."""


def build_body_sway_preview_capture_plan_v2(
    inputs: BodySwayPreviewInputsV2,
    projection: BodySwayPreviewProjectionV2,
) -> dict[str, Any]:
    """Select the legacy stills under the exact reviewed world viewport."""

    try:
        if type(inputs) is not BodySwayPreviewInputsV2 \
                or type(projection) is not BodySwayPreviewProjectionV2:
            raise BodySwayPreviewCapturePlanV2Error(
                "Capture planning v2 requires exact v2 inputs and projection"
            )
        metadata = projection.public_metadata
        expected = {
            "capture_framing_candidate_sha256":
                inputs.framing_candidate_sha256,
            "capture_framing_decision_sha256":
                inputs.framing_decision_sha256,
            "capture_framing_revision": inputs.framing_revision,
            "world_viewport": inputs.world_viewport,
        }
        if metadata["projection_sha256"] != projection.sha256 \
                or any(metadata[field] != value
                       for field, value in expected.items()) \
                or metadata["probe_tick_schedule_sha256"] \
                != inputs.report["schedule"]["tick_schedule_sha256"]:
            raise BodySwayPreviewCapturePlanV2Error(
                "Capture projection differs from reviewed v2 framing"
            )
        ticks = select_body_sway_preview_capture_ticks(
            inputs.timing, inputs.selection, projection.sample_ticks,
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
            raise BodySwayPreviewCapturePlanV2Error(
                "Body-sway capture v2 case count exceeds the fixed profile"
            )
        body = {
            "source": {
                "preview_projection_sha256": projection.sha256,
                "capture_framing_candidate_sha256":
                    inputs.framing_candidate_sha256,
                "capture_framing_decision_sha256":
                    inputs.framing_decision_sha256,
                "capture_framing_revision": inputs.framing_revision,
            },
            "viewport": dict(CAPTURE_VIEWPORT),
            "device_pixel_ratio": CAPTURE_DEVICE_PIXEL_RATIO,
            "background": DEFAULT_BACKGROUND,
            "preserve_drawing_buffer": True,
            "world_viewport": inputs.world_viewport,
            "selection_scope":
                "capture-framed-bounded-stills-for-manual-review-v2",
            "cases": cases,
        }
        return {
            "capture_plan_sha256": canonical_sha256({
                "domain": CAPTURE_PLAN_DIGEST_DOMAIN, **body,
            }),
            **body,
        }
    except BodySwayPreviewCapturePlanV2Error:
        raise
    except (
        KeyError, OverflowError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayPreviewCapturePlanV2Error(
            f"Body-sway preview capture planning v2 failed: {exc}"
        ) from exc


def body_sway_capture_plan_sha256_v2(plan: dict[str, Any]) -> str:
    """Recompute the v2 domain-separated plan identity."""

    try:
        body = json.loads(json.dumps(
            plan, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ))
        supplied = body.pop("capture_plan_sha256", None)
        result = canonical_sha256({
            "domain": CAPTURE_PLAN_DIGEST_DOMAIN, **body,
        })
        if supplied != result:
            raise BodySwayPreviewCapturePlanV2Error(
                "Body-sway capture plan v2 digest is inconsistent"
            )
        return result
    except BodySwayPreviewCapturePlanV2Error:
        raise
    except (OverflowError, TypeError, UnicodeError, ValueError) as exc:
        raise BodySwayPreviewCapturePlanV2Error(
            f"Body-sway capture plan v2 validation failed: {exc}"
        ) from exc


def _case(identifier, animation, tick, timing):
    return {
        "case_id": identifier,
        "animation": animation,
        "tick": tick,
        "time_seconds": tick / timing["ticks_per_second"],
    }
