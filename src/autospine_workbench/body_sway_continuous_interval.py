"""Conservative continuous proof over one sampled-linear body-sway segment.

The sole gain domain is the coupled four-bone ray ``lambda in [0, 1]``.
Adaptive interval subdivision is used to tighten outward bounds; it is not
dense sampling.  Any terminal box that cannot be certified makes the whole
segment ``indeterminate``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from .body_sway_continuous_interval_geometry import (
    BodySwayIntervalBoxAssessment,
    BodySwayIntervalGeometryBounds,
    assess_body_sway_interval_box,
)
from .body_sway_interval_arithmetic import OutwardInterval
from .body_sway_probe_geometry_context import PreparedBodySwayGeometryContext
from .body_sway_probe_geometry_inputs import (
    BodySwayProbeGeometryError,
    normalize_body_sway_pose_sample,
)
from .body_sway_probe_math import BodySwayPoseSample
from .idle_behavior_inventory import BODY_BONE_IDS


DEFAULT_MAX_DEPTH = 14
DEFAULT_MAX_BOXES = 32_768
PROGRESS_BOX_STRIDE = 256
MAX_ALLOWED_DEPTH = 20
MAX_ALLOWED_BOXES = 262_144
SCOPE = (
    "sampled_linear_segment_fk",
    "continuous_canvas_containment",
    "continuous_mesh_deformation",
    "shared_index_internal_continuity",
)
EXCLUSIONS = (
    "upstream_preview_key_adjacency_binding",
    "platform_libm_equivalence",
    "inter_attachment_seams",
    "raster_visual_quality",
    "runtime_equivalence",
    "publishable_timeline",
    "release_authority",
)


class BodySwayContinuousIntervalError(ValueError):
    """Raised when a segment cannot be admitted without guessing."""


@dataclass(frozen=True, slots=True)
class BodySwayIntervalProofBudget:
    """A bounded effort limit; lowering it can only yield indeterminate."""

    max_depth: int = DEFAULT_MAX_DEPTH
    max_boxes: int = DEFAULT_MAX_BOXES

    def __post_init__(self) -> None:
        if type(self.max_depth) is not int \
                or not 0 <= self.max_depth <= MAX_ALLOWED_DEPTH \
                or type(self.max_boxes) is not int \
                or not 1 <= self.max_boxes <= MAX_ALLOWED_BOXES:
            raise BodySwayContinuousIntervalError(
                "Continuous interval proof budget is invalid"
            )


@dataclass(frozen=True, slots=True)
class BodySwayContinuousIntervalProof:
    """Detached evidence for one supplied endpoint segment.

    A higher contract must prove that these endpoints are adjacent preview
    keys before composing this mathematical result into P10 evidence.
    """

    left_tick: int
    right_tick: int
    status: str
    reason_codes: tuple[str, ...]
    bounds: BodySwayIntervalGeometryBounds
    evaluated_box_count: int
    certified_terminal_box_count: int
    indeterminate_terminal_box_count: int
    maximum_depth_reached: int
    attachment_count: int
    vertex_count: int
    triangle_count: int
    edge_count: int
    time_model: str = "sampled-linear-over-supplied-endpoint-segment"
    gain_model: str = "coupled-four-bone-lambda-in-closed-unit-interval"
    rounding_profile: str = (
        "binary64-directed-basic-ops-rational-trig-q9-q4096-v1"
    )
    proof_method: str = "adaptive-interval-box-subdivision-no-point-sampling"
    numeric_enclosure_profile: str = "q9-per-layer-plus-q4096-half-step-v1"
    scope: tuple[str, ...] = SCOPE
    exclusions: tuple[str, ...] = EXCLUSIONS

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class _Box:
    time_fraction: OutwardInterval
    gain: OutwardInterval
    depth: int


def prove_body_sway_sampled_linear_segment(
    context: PreparedBodySwayGeometryContext,
    left: BodySwayPoseSample,
    right: BodySwayPoseSample,
    *,
    budget: BodySwayIntervalProofBudget | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> BodySwayContinuousIntervalProof:
    """Prove one segment; upstream must separately bind key adjacency."""

    try:
        admitted = _admit(context, left, right)
        limits = BodySwayIntervalProofBudget() if budget is None else budget
        if type(limits) is not BodySwayIntervalProofBudget:
            raise BodySwayContinuousIntervalError(
                "Continuous interval proof budget must be exact"
            )
        if on_progress is not None and not callable(on_progress):
            raise BodySwayContinuousIntervalError(
                "Continuous interval proof progress callback is invalid"
            )
        return _prove(
            context, left, right, admitted, limits, on_progress,
        )
    except BodySwayContinuousIntervalError:
        raise
    except BodySwayProbeGeometryError as exc:
        raise BodySwayContinuousIntervalError(str(exc)) from exc
    except (AttributeError, KeyError, OverflowError, TypeError, ValueError) as exc:
        raise BodySwayContinuousIntervalError(
            f"Continuous interval proof failed: {exc}"
        ) from exc


def _admit(context, left, right):
    if type(context) is not PreparedBodySwayGeometryContext:
        raise BodySwayContinuousIntervalError(
            "Continuous interval proof context is invalid"
        )
    normalize_body_sway_pose_sample(left, context.bone_ids)
    normalize_body_sway_pose_sample(right, context.bone_ids)
    if left.tick >= right.tick:
        raise BodySwayContinuousIntervalError(
            "Continuous interval segment ticks are not increasing"
        )
    if tuple(row[0] for row in left.base_rotation_deg) \
            != tuple(row[0] for row in right.base_rotation_deg) \
            or tuple(row[0] for row in left.overlay_rotation_deg) \
            != BODY_BONE_IDS \
            or tuple(row[0] for row in right.overlay_rotation_deg) \
            != BODY_BONE_IDS:
        raise BodySwayContinuousIntervalError(
            "Continuous interval endpoint inventories differ"
        )
    return {
        "left_base": dict(left.base_rotation_deg),
        "right_base": dict(right.base_rotation_deg),
        "left_overlay": dict(left.overlay_rotation_deg),
        "right_overlay": dict(right.overlay_rotation_deg),
    }


def _prove(context, left, right, admitted, limits, on_progress):
    pending = [_Box(
        OutwardInterval(0.0, 1.0), OutwardInterval(0.0, 1.0), 0,
    )]
    terminal: list[BodySwayIntervalBoxAssessment] = []
    evaluated = certified = indeterminate = maximum_depth = 0
    terminal_reasons: set[str] = set()
    while pending:
        box = pending.pop()
        assessment = assess_body_sway_interval_box(
            context,
            left_base_rotation_deg=admitted["left_base"],
            right_base_rotation_deg=admitted["right_base"],
            left_overlay_rotation_deg=admitted["left_overlay"],
            right_overlay_rotation_deg=admitted["right_overlay"],
            left_root_translation_xy=left.root_translation_xy,
            right_root_translation_xy=right.root_translation_xy,
            time_fraction=box.time_fraction, gain=box.gain,
        )
        evaluated += 1
        if on_progress is not None and (
            evaluated == 1 or evaluated % PROGRESS_BOX_STRIDE == 0
        ):
            on_progress(evaluated, limits.max_boxes)
        maximum_depth = max(maximum_depth, box.depth)
        if assessment.status == "certified":
            certified += 1
            terminal.append(assessment)
            continue
        stop_reason = _stop_reason(box, pending, evaluated, limits)
        children = None if stop_reason else _split(box)
        if children is not None:
            pending.extend(reversed(children))
            continue
        indeterminate += 1
        terminal.append(assessment)
        terminal_reasons.update(assessment.reason_codes)
        terminal_reasons.add(stop_reason or "parameter_resolution_exhausted")
    status = (
        "continuous_structural_certified"
        if indeterminate == 0 else "indeterminate"
    )
    if on_progress is not None and evaluated != 1 \
            and evaluated % PROGRESS_BOX_STRIDE:
        on_progress(evaluated, limits.max_boxes)
    first = terminal[0]
    return BodySwayContinuousIntervalProof(
        left_tick=left.tick, right_tick=right.tick, status=status,
        reason_codes=tuple(sorted(terminal_reasons)),
        bounds=_aggregate_bounds(terminal),
        evaluated_box_count=evaluated,
        certified_terminal_box_count=certified,
        indeterminate_terminal_box_count=indeterminate,
        maximum_depth_reached=maximum_depth,
        attachment_count=first.attachment_count,
        vertex_count=first.vertex_count,
        triangle_count=first.triangle_count,
        edge_count=first.edge_count,
    )


def _stop_reason(box, pending, evaluated, limits):
    if box.depth >= limits.max_depth:
        return "subdivision_depth_exhausted"
    if evaluated + len(pending) + 2 > limits.max_boxes:
        return "subdivision_box_budget_exhausted"
    return None


def _split(box):
    primary = box.time_fraction if box.depth % 2 == 0 else box.gain
    secondary = box.gain if box.depth % 2 == 0 else box.time_fraction
    halves = primary.bisect()
    primary_is_time = box.depth % 2 == 0
    if halves is None:
        halves = secondary.bisect()
        primary_is_time = not primary_is_time
    if halves is None:
        return None
    if primary_is_time:
        return tuple(_Box(half, box.gain, box.depth + 1)
                     for half in halves)
    return tuple(_Box(box.time_fraction, half, box.depth + 1)
                 for half in halves)


def _aggregate_bounds(rows):
    canvas = [row.bounds.canvas_margin_lower_px for row in rows
              if row.bounds.canvas_margin_lower_px is not None]
    minimum = [row.bounds.min_signed_area_ratio_lower for row in rows
               if row.bounds.min_signed_area_ratio_lower is not None]
    maximum = [row.bounds.max_signed_area_ratio_upper for row in rows
               if row.bounds.max_signed_area_ratio_upper is not None]
    stretch = [row.bounds.max_edge_stretch_squared_ratio_upper for row in rows
               if row.bounds.max_edge_stretch_squared_ratio_upper is not None]
    return BodySwayIntervalGeometryBounds(
        canvas_margin_lower_px=min(canvas) if canvas else None,
        min_signed_area_ratio_lower=min(minimum) if minimum else None,
        max_signed_area_ratio_upper=max(maximum) if maximum else None,
        max_edge_stretch_squared_ratio_upper=(
            max(stretch) if stretch else None
        ),
    )
