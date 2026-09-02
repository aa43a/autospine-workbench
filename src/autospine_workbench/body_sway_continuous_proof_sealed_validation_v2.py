"""Cheap sealed-result checks for P10.4b2 v2, excluding interval replay."""

from __future__ import annotations

from collections.abc import Mapping

from .body_sway_continuous_backend_validation import (
    require_body_sway_interval_backend_result,
)
from .body_sway_continuous_interval import (
    BodySwayContinuousIntervalProof, BodySwayIntervalProofBudget,
)
from .body_sway_continuous_interval_geometry import (
    BodySwayIntervalGeometryBounds,
)
from .body_sway_continuous_proof_analysis import _summary
from .body_sway_continuous_proof_profile_v2 import (
    continuous_analyzer_profile_v2, continuous_claims_v2,
    continuous_problem_v2, continuous_proof_budget_v2,
    continuous_release_gate_v2, continuous_segment_sha256_v2,
)
from .body_sway_probe_geometry_context import (
    PreparedBodySwayGeometryContext, PreparedBodySwayMesh,
)


_FIELDS = {
    "left_tick", "right_tick", "status", "reason_codes", "bounds",
    "evaluated_box_count", "certified_terminal_box_count",
    "indeterminate_terminal_box_count", "maximum_depth_reached",
    "attachment_count", "vertex_count", "triangle_count", "edge_count",
    "time_model", "gain_model", "rounding_profile", "proof_method",
    "numeric_enclosure_profile", "scope", "exclusions",
    "segment_evidence_sha256",
}
class BodySwayContinuousSealedValidationV2Error(ValueError):
    """Raised when sealed proof fields are internally inconsistent."""


def require_body_sway_continuous_sealed_analysis_v2(
    root: Mapping, source: Mapping, context: PreparedBodySwayGeometryContext,
) -> None:
    try:
        ticks = source["preview_projection_v2"]["sample_ticks"]
        if root.get("problem") != continuous_problem_v2(
            source["source_set_sha256"], list(ticks),
        ):
            raise BodySwayContinuousSealedValidationV2Error(
                "Continuous proof v2 problem differs"
            )
        segments = root.get("segments")
        pairs = list(zip(ticks, ticks[1:]))
        if not isinstance(segments, list) or len(segments) != len(pairs):
            raise BodySwayContinuousSealedValidationV2Error(
                "Continuous proof v2 segment schedule differs"
            )
        budget = continuous_proof_budget_v2()
        used_boxes, halted = 0, False
        for row, pair in zip(segments, pairs, strict=True):
            used_boxes, halted = _segment(
                row, pair, context, budget, used_boxes, halted,
            )
        certified = bool(segments) and all(
            row["status"] == "continuous_structural_certified"
            for row in segments
        )
        status = "continuous_preview_model_structural_certified" \
            if certified else "indeterminate"
        expected = {
            "analyzer": continuous_analyzer_profile_v2(),
            "claims": continuous_claims_v2(certified), "status": status,
            "release_gate": continuous_release_gate_v2(certified),
            "summary": _summary(segments),
        }
        if any(root.get(field) != value for field, value in expected.items()):
            raise BodySwayContinuousSealedValidationV2Error(
                "Continuous proof v2 sealed analysis differs"
            )
        if expected["summary"]["evaluated_box_count"] \
                > continuous_proof_budget_v2()["max_total_boxes"]:
            raise BodySwayContinuousSealedValidationV2Error(
                "Continuous proof v2 global box budget is exceeded"
            )
    except BodySwayContinuousSealedValidationV2Error:
        raise
    except Exception as exc:
        raise BodySwayContinuousSealedValidationV2Error(
            f"Continuous proof v2 sealed validation failed: {exc}"
        ) from exc


def _segment(row, pair, context, budget_values, used_boxes, halted):
    if not isinstance(row, Mapping) or set(row) != _FIELDS \
            or (row.get("left_tick"), row.get("right_tick")) != pair \
            or row.get("segment_evidence_sha256") \
                != continuous_segment_sha256_v2(row):
        raise BodySwayContinuousSealedValidationV2Error(
            "Continuous proof v2 segment identity differs"
        )
    if row.get("evaluated_box_count") == 0:
        _special_segment(row, context)
        reason = row["reason_codes"]
        if reason == ["interval_backend_error"]:
            if halted or used_boxes >= budget_values["max_total_boxes"]:
                raise BodySwayContinuousSealedValidationV2Error(
                    "Continuous proof v2 backend fallback order differs"
                )
            return budget_values["max_total_boxes"], True
        if not halted and used_boxes < budget_values["max_total_boxes"]:
            raise BodySwayContinuousSealedValidationV2Error(
                "Continuous proof v2 global fallback precedes exhaustion"
            )
        return used_boxes, True
    remaining = budget_values["max_total_boxes"] - used_boxes
    if halted or remaining <= 0:
        raise BodySwayContinuousSealedValidationV2Error(
            "Continuous proof v2 evaluates after global exhaustion"
        )
    proof = _proof(row)
    budget = BodySwayIntervalProofBudget(
        max_depth=budget_values["max_depth"],
        max_boxes=min(budget_values["max_boxes_per_segment"], remaining),
    )
    validated = require_body_sway_interval_backend_result(
        proof, context=context, left_tick=pair[0], right_tick=pair[1],
        budget=budget,
    )
    # ``BodySwayContinuousIntervalProof.to_dict()`` preserves tuple fields,
    # while the sealed document has already passed through canonical JSON and
    # therefore contains arrays.  Normalize only those representation fields
    # before the exact comparison; their values were validated above.
    for field in ("reason_codes", "scope", "exclusions"):
        validated[field] = list(validated[field])
    validated["segment_evidence_sha256"] = row["segment_evidence_sha256"]
    if validated != row:
        raise BodySwayContinuousSealedValidationV2Error(
            "Continuous proof v2 segment fields differ"
        )
    return used_boxes + row["evaluated_box_count"], False


def _special_segment(row, context):
    expected_counts = _geometry_counts(context)
    bounds = row.get("bounds")
    if row.get("status") != "indeterminate" \
            or row.get("reason_codes") not in (
                ["global_subdivision_box_budget_exhausted"],
                ["interval_backend_error"],
            ) \
            or not isinstance(bounds, Mapping) \
            or set(bounds) != {
                "canvas_margin_lower_px", "min_signed_area_ratio_lower",
                "max_signed_area_ratio_upper",
                "max_edge_stretch_squared_ratio_upper",
            } \
            or any(value is not None for value in bounds.values()) \
            or tuple(row.get(field) for field in (
                "certified_terminal_box_count",
                "indeterminate_terminal_box_count", "maximum_depth_reached",
            )) != (0, 1, 0) \
            or tuple(row.get(field) for field in (
                "attachment_count", "vertex_count", "triangle_count",
                "edge_count",
            )) != expected_counts:
        raise BodySwayContinuousSealedValidationV2Error(
            "Continuous proof v2 fallback segment is invalid"
        )
    fixed = _proof_fixed(row)
    if fixed != _proof_fixed(_proof_template()):
        raise BodySwayContinuousSealedValidationV2Error(
            "Continuous proof v2 fallback profile differs"
        )


def _proof(row):
    bounds = row["bounds"]
    return BodySwayContinuousIntervalProof(
        left_tick=row["left_tick"], right_tick=row["right_tick"],
        status=row["status"], reason_codes=tuple(row["reason_codes"]),
        bounds=BodySwayIntervalGeometryBounds(
            bounds["canvas_margin_lower_px"],
            bounds["min_signed_area_ratio_lower"],
            bounds["max_signed_area_ratio_upper"],
            bounds["max_edge_stretch_squared_ratio_upper"],
        ),
        evaluated_box_count=row["evaluated_box_count"],
        certified_terminal_box_count=row["certified_terminal_box_count"],
        indeterminate_terminal_box_count=
            row["indeterminate_terminal_box_count"],
        maximum_depth_reached=row["maximum_depth_reached"],
        attachment_count=row["attachment_count"],
        vertex_count=row["vertex_count"], triangle_count=row["triangle_count"],
        edge_count=row["edge_count"], time_model=row["time_model"],
        gain_model=row["gain_model"], rounding_profile=row["rounding_profile"],
        proof_method=row["proof_method"],
        numeric_enclosure_profile=row["numeric_enclosure_profile"],
        scope=tuple(row["scope"]), exclusions=tuple(row["exclusions"]),
    )


def _geometry_counts(context):
    meshes = [row for row in context.attachments
              if type(row) is PreparedBodySwayMesh]
    return (
        len(context.attachments),
        sum(len(row.setup_vertices_xy) for row in context.attachments),
        sum(len(row.deformation.triangles) for row in meshes),
        sum(len(row.deformation.edges) for row in meshes),
    )


def _proof_fixed(row):
    return tuple(row[field] for field in (
        "time_model", "gain_model", "rounding_profile", "proof_method",
        "numeric_enclosure_profile", "scope", "exclusions",
    ))


def _proof_template():
    return {
        "time_model": "sampled-linear-over-supplied-endpoint-segment",
        "gain_model": "coupled-four-bone-lambda-in-closed-unit-interval",
        "rounding_profile":
            "binary64-directed-basic-ops-rational-trig-q9-q4096-v1",
        "proof_method": "adaptive-interval-box-subdivision-no-point-sampling",
        "numeric_enclosure_profile": "q9-per-layer-plus-q4096-half-step-v1",
        "scope": [
            "sampled_linear_segment_fk", "continuous_canvas_containment",
            "continuous_mesh_deformation", "shared_index_internal_continuity",
        ],
        "exclusions": [
            "upstream_preview_key_adjacency_binding",
            "platform_libm_equivalence", "inter_attachment_seams",
            "raster_visual_quality", "runtime_equivalence",
            "publishable_timeline", "release_authority",
        ],
    }


__all__ = [
    "BodySwayContinuousSealedValidationV2Error",
    "require_body_sway_continuous_sealed_analysis_v2",
]
