"""Interval FK/LBS structural bounds for one sampled-linear parameter box.

This module only evaluates the workbench preview model.  It does not prove
Spine runtime equivalence, raster quality, attachment seams, or release safety.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from .body_sway_interval_arithmetic import (
    OutwardInterval,
    round_down,
    round_up,
)
from .body_sway_interval_pose import (
    IntervalPoint,
    prepare_body_sway_interval_pose,
    skin_body_sway_interval_binding,
)
from .body_sway_probe_geometry_context import (
    PreparedBodySwayGeometryContext,
    PreparedBodySwayMesh,
    PreparedBodySwayRegion,
)
from .mesh_deformation_metrics import SETUP_AREA_EPSILON

@dataclass(frozen=True, slots=True)
class BodySwayIntervalGeometryBounds:
    """Worst outward structural bounds over one time/gain box."""

    canvas_margin_lower_px: float | None
    min_signed_area_ratio_lower: float | None
    max_signed_area_ratio_upper: float | None
    max_edge_stretch_squared_ratio_upper: float | None


@dataclass(frozen=True, slots=True)
class BodySwayIntervalBoxAssessment:
    """One conservative box assessment; failure means only unproved."""

    status: str
    reason_codes: tuple[str, ...]
    bounds: BodySwayIntervalGeometryBounds
    attachment_count: int
    vertex_count: int
    triangle_count: int
    edge_count: int


def assess_body_sway_interval_box(
    context: PreparedBodySwayGeometryContext,
    *,
    left_base_rotation_deg: dict[str, float],
    right_base_rotation_deg: dict[str, float],
    left_overlay_rotation_deg: dict[str, float],
    right_overlay_rotation_deg: dict[str, float],
    left_root_translation_xy: tuple[float, float],
    right_root_translation_xy: tuple[float, float],
    time_fraction: OutwardInterval,
    gain: OutwardInterval,
) -> BodySwayIntervalBoxAssessment:
    """Propagate a closed time/gain box through exact prepared geometry."""

    if type(context) is not PreparedBodySwayGeometryContext:
        raise ValueError("Continuous interval geometry context is invalid")
    pose = prepare_body_sway_interval_pose(
        context,
        left_base_rotation_deg=left_base_rotation_deg,
        right_base_rotation_deg=right_base_rotation_deg,
        left_overlay_rotation_deg=left_overlay_rotation_deg,
        right_overlay_rotation_deg=right_overlay_rotation_deg,
        left_root_translation_xy=left_root_translation_xy,
        right_root_translation_xy=right_root_translation_xy,
        time_fraction=time_fraction, gain=gain,
    )
    reasons: set[str] = set()
    canvas_margin = math.inf
    minimum_area, maximum_area, maximum_stretch = math.inf, -math.inf, -math.inf
    vertex_count = triangle_count = edge_count = 0
    for attachment in context.attachments:
        vertices = skin_body_sway_interval_binding(pose, attachment.binding)
        vertex_count += len(vertices)
        for vertex in vertices:
            margin = _canvas_margin(vertex, context.canvas_size)
            canvas_margin = min(canvas_margin, margin)
            if margin < 0.0:
                reasons.add("canvas_containment_unproven")
            if not vertex[0].finite or not vertex[1].finite:
                reasons.add("non_finite_interval_bound")
        if type(attachment) is PreparedBodySwayRegion:
            continue
        if type(attachment) is not PreparedBodySwayMesh:
            raise ValueError("Continuous interval attachment is invalid")
        prepared = attachment.deformation
        triangle_count += len(prepared.triangles)
        edge_count += len(prepared.edges)
        for triangle, setup_area in zip(
            prepared.triangles, prepared.setup_areas, strict=True,
        ):
            posed_area = _signed_area(vertices, triangle)
            ratio = posed_area.divide_positive(setup_area)
            minimum_area = min(minimum_area, ratio.lower)
            maximum_area = max(maximum_area, ratio.upper)
            if posed_area.lower <= SETUP_AREA_EPSILON:
                reasons.add("absolute_triangle_area_unproven")
            if ratio.lower <= prepared.min_area_ratio:
                reasons.add("minimum_area_ratio_unproven")
            if ratio.upper >= prepared.max_area_ratio:
                reasons.add("maximum_area_ratio_unproven")
        for edge, setup_length in zip(
            prepared.edges, prepared.setup_edge_lengths, strict=True,
        ):
            squared = _edge_squared(vertices, edge)
            squared_ratio_upper = _squared_ratio_upper(
                squared, setup_length
            )
            maximum_stretch = max(maximum_stretch, squared_ratio_upper)
            distance_limit = (
                OutwardInterval.point(setup_length)
                * OutwardInterval.point(prepared.max_edge_stretch)
            ).square().lower
            if squared.upper >= distance_limit:
                reasons.add("maximum_edge_stretch_unproven")
    if any(not matrix_value.finite for matrix in pose.skin_matrices
           for matrix_value in matrix):
        reasons.add("non_finite_interval_bound")
    if vertex_count == 0:
        reasons.add("empty_attachment_geometry")
    bounds = BodySwayIntervalGeometryBounds(
        canvas_margin_lower_px=(
            None if canvas_margin == math.inf else canvas_margin
        ),
        min_signed_area_ratio_lower=(
            None if minimum_area == math.inf else minimum_area
        ),
        max_signed_area_ratio_upper=(
            None if maximum_area == -math.inf else maximum_area
        ),
        max_edge_stretch_squared_ratio_upper=(
            None if maximum_stretch == -math.inf else maximum_stretch
        ),
    )
    return BodySwayIntervalBoxAssessment(
        status="certified" if not reasons else "indeterminate",
        reason_codes=tuple(sorted(reasons)), bounds=bounds,
        attachment_count=len(context.attachments),
        vertex_count=vertex_count, triangle_count=triangle_count,
        edge_count=edge_count,
    )

def _canvas_margin(vertex, canvas) -> float:
    x, y = vertex
    return min(
        x.lower, y.lower,
        round_down(canvas[0] - x.upper),
        round_down(canvas[1] - y.upper),
    )


def _signed_area(vertices, triangle) -> OutwardInterval:
    first, second, third = (vertices[index] for index in triangle)
    cross = ((second[0] - first[0]) * (third[1] - first[1])
             - (second[1] - first[1]) * (third[0] - first[0]))
    return cross * OutwardInterval.point(0.5)


def _edge_squared(vertices, edge) -> OutwardInterval:
    left, right = (vertices[index] for index in edge)
    return (right[0] - left[0]).square() \
        + (right[1] - left[1]).square()


def _squared_ratio_upper(squared, setup_length) -> float:
    setup_squared_lower = OutwardInterval.point(setup_length).square().lower
    if setup_squared_lower <= 0.0:
        return math.inf
    return round_up(squared.upper / setup_squared_lower)
