"""Fail-closed validation of one P10.4b2 interval backend result."""

from __future__ import annotations

import math

from .body_sway_continuous_interval import (
    EXCLUSIONS,
    SCOPE,
    BodySwayContinuousIntervalProof,
    BodySwayIntervalProofBudget,
)
from .body_sway_continuous_interval_geometry import (
    BodySwayIntervalGeometryBounds,
)
from .body_sway_probe_geometry_context import (
    PreparedBodySwayGeometryContext,
    PreparedBodySwayMesh,
)
from .body_sway_probe_profile import (
    MAX_AREA_RATIO,
    MAX_EDGE_STRETCH,
    MIN_AREA_RATIO,
)
from .mesh_deformation_metrics import SETUP_AREA_EPSILON


_STATUSES = {"continuous_structural_certified", "indeterminate"}
_REASONS = {
    "absolute_triangle_area_unproven",
    "canvas_containment_unproven",
    "empty_attachment_geometry",
    "maximum_area_ratio_unproven",
    "maximum_edge_stretch_unproven",
    "minimum_area_ratio_unproven",
    "non_finite_interval_bound",
    "parameter_resolution_exhausted",
    "subdivision_box_budget_exhausted",
    "subdivision_depth_exhausted",
}
_FIXED = {
    "time_model": "sampled-linear-over-supplied-endpoint-segment",
    "gain_model": "coupled-four-bone-lambda-in-closed-unit-interval",
    "rounding_profile": (
        "binary64-directed-basic-ops-rational-trig-q9-q4096-v1"
    ),
    "proof_method": "adaptive-interval-box-subdivision-no-point-sampling",
    "numeric_enclosure_profile": "q9-per-layer-plus-q4096-half-step-v1",
}


class BodySwayContinuousBackendValidationError(ValueError):
    """Raised when the interval backend violates its pure return contract."""


def require_body_sway_interval_backend_result(
    proof: object,
    *,
    context: PreparedBodySwayGeometryContext,
    left_tick: int,
    right_tick: int,
    budget: BodySwayIntervalProofBudget,
) -> dict:
    """Return a detached row only after every backend invariant is checked."""

    if type(proof) is not BodySwayContinuousIntervalProof \
            or type(context) is not PreparedBodySwayGeometryContext \
            or type(budget) is not BodySwayIntervalProofBudget:
        raise BodySwayContinuousBackendValidationError(
            "Continuous interval backend result types are invalid"
        )
    _require_identity_and_fixed(proof, left_tick, right_tick)
    _require_reasons_and_counters(proof, budget)
    _require_geometry_counts(proof, context)
    _require_bounds(proof, context)
    return proof.to_dict()


def _require_identity_and_fixed(proof, left_tick, right_tick):
    if type(proof.left_tick) is not int or proof.left_tick != left_tick \
            or type(proof.right_tick) is not int \
            or proof.right_tick != right_tick \
            or proof.left_tick >= proof.right_tick \
            or proof.status not in _STATUSES:
        raise BodySwayContinuousBackendValidationError(
            "Continuous interval backend identity or status is invalid"
        )
    for field, expected in _FIXED.items():
        if getattr(proof, field) != expected:
            raise BodySwayContinuousBackendValidationError(
                f"Continuous interval backend {field} is invalid"
            )
    if proof.scope != SCOPE or proof.exclusions != EXCLUSIONS:
        raise BodySwayContinuousBackendValidationError(
            "Continuous interval backend scope is invalid"
        )


def _require_reasons_and_counters(proof, budget):
    reasons = proof.reason_codes
    if type(reasons) is not tuple \
            or reasons != tuple(sorted(set(reasons))) \
            or any(type(reason) is not str or reason not in _REASONS
                   for reason in reasons):
        raise BodySwayContinuousBackendValidationError(
            "Continuous interval backend reasons are invalid"
        )
    names = (
        "evaluated_box_count", "certified_terminal_box_count",
        "indeterminate_terminal_box_count", "maximum_depth_reached",
    )
    if any(type(getattr(proof, name)) is not int for name in names):
        raise BodySwayContinuousBackendValidationError(
            "Continuous interval backend counters are invalid"
        )
    terminal = (proof.certified_terminal_box_count
                + proof.indeterminate_terminal_box_count)
    if not 1 <= proof.evaluated_box_count <= budget.max_boxes \
            or proof.certified_terminal_box_count < 0 \
            or proof.indeterminate_terminal_box_count < 0 \
            or terminal < 1 \
            or proof.evaluated_box_count != 2 * terminal - 1 \
            or not 0 <= proof.maximum_depth_reached <= budget.max_depth:
        raise BodySwayContinuousBackendValidationError(
            "Continuous interval backend counters exceed the proof budget"
        )
    certified = proof.status == "continuous_structural_certified"
    if certified != (proof.indeterminate_terminal_box_count == 0) \
            or certified != (len(reasons) == 0):
        raise BodySwayContinuousBackendValidationError(
            "Continuous interval backend status disagrees with terminals"
        )


def _require_geometry_counts(proof, context):
    meshes = [row for row in context.attachments
              if type(row) is PreparedBodySwayMesh]
    expected = (
        len(context.attachments),
        sum(len(row.setup_vertices_xy) for row in context.attachments),
        sum(len(row.deformation.triangles) for row in meshes),
        sum(len(row.deformation.edges) for row in meshes),
    )
    actual = (
        proof.attachment_count, proof.vertex_count,
        proof.triangle_count, proof.edge_count,
    )
    if any(type(value) is not int for value in actual) or actual != expected:
        raise BodySwayContinuousBackendValidationError(
            "Continuous interval backend geometry counts are invalid"
        )
    if proof.attachment_count < 1 or proof.vertex_count < 1:
        raise BodySwayContinuousBackendValidationError(
            "Continuous interval backend geometry is empty"
        )


def _require_bounds(proof, context):
    bounds = proof.bounds
    if type(bounds) is not BodySwayIntervalGeometryBounds:
        raise BodySwayContinuousBackendValidationError(
            "Continuous interval backend bounds are invalid"
        )
    values = (
        bounds.canvas_margin_lower_px,
        bounds.min_signed_area_ratio_lower,
        bounds.max_signed_area_ratio_upper,
        bounds.max_edge_stretch_squared_ratio_upper,
    )
    if any(value is not None and (
        type(value) is not float or not math.isfinite(value)
    ) for value in values):
        raise BodySwayContinuousBackendValidationError(
            "Continuous interval backend bounds must be finite"
        )
    if bounds.canvas_margin_lower_px is None:
        raise BodySwayContinuousBackendValidationError(
            "Continuous interval backend omitted the canvas bound"
        )
    if proof.triangle_count == 0:
        if bounds.min_signed_area_ratio_lower is not None \
                or bounds.max_signed_area_ratio_upper is not None:
            raise BodySwayContinuousBackendValidationError(
                "Triangle-free interval backend returned area bounds"
            )
    elif bounds.min_signed_area_ratio_lower is None \
            or bounds.max_signed_area_ratio_upper is None:
        raise BodySwayContinuousBackendValidationError(
            "Mesh interval backend omitted area bounds"
        )
    if proof.edge_count == 0:
        if bounds.max_edge_stretch_squared_ratio_upper is not None:
            raise BodySwayContinuousBackendValidationError(
                "Edge-free interval backend returned a stretch bound"
            )
    elif bounds.max_edge_stretch_squared_ratio_upper is None:
        raise BodySwayContinuousBackendValidationError(
            "Mesh interval backend omitted the stretch bound"
        )
    if proof.status == "continuous_structural_certified":
        _require_certified_bounds(values, proof.triangle_count, context)


def _require_certified_bounds(values, triangle_count, context):
    canvas, minimum, maximum, stretch_squared = values
    if canvas is None or canvas < 0.0:
        raise BodySwayContinuousBackendValidationError(
            "Certified interval does not prove canvas containment"
        )
    area_unsafe = triangle_count and (
        minimum <= MIN_AREA_RATIO or maximum >= MAX_AREA_RATIO
    )
    stretch_unsafe = stretch_squared is not None \
        and stretch_squared >= MAX_EDGE_STRETCH * MAX_EDGE_STRETCH
    if area_unsafe or stretch_unsafe:
        raise BodySwayContinuousBackendValidationError(
            "Certified interval does not satisfy mesh thresholds"
        )
    setup_areas = [
        area
        for attachment in context.attachments
        if type(attachment) is PreparedBodySwayMesh
        for area in attachment.deformation.setup_areas
    ]
    if triangle_count:
        absolute_lower = math.nextafter(
            minimum * min(setup_areas), -math.inf
        )
        if absolute_lower <= SETUP_AREA_EPSILON:
            raise BodySwayContinuousBackendValidationError(
                "Certified interval does not prove absolute triangle area"
            )
