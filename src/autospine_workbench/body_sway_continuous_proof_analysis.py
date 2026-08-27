"""Full-preview P10.4b2 continuous sampled-linear interval analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .body_sway_continuous_interval import (
    BodySwayContinuousIntervalError,
    BodySwayIntervalProofBudget,
    prove_body_sway_sampled_linear_segment,
)
from .body_sway_continuous_backend_validation import (
    BodySwayContinuousBackendValidationError,
    require_body_sway_interval_backend_result,
)
from .body_sway_continuous_proof_profile import (
    body_sway_continuous_proof_budget,
    body_sway_continuous_proof_claims,
    body_sway_continuous_proof_problem,
    body_sway_continuous_segment_sha256,
)
from .body_sway_continuous_proof_source import (
    BodySwayContinuousSourceError,
    require_body_sway_continuous_source,
)
from .body_sway_probe_geometry_context import (
    PreparedBodySwayMesh,
    prepare_body_sway_geometry_context,
)
from .body_sway_probe_sampler import prepare_body_sway_sampler


class BodySwayContinuousProofAnalysisError(ValueError):
    """Raised when exact sources cannot define a bounded proof problem."""


@dataclass(frozen=True, slots=True)
class BodySwayContinuousProofAnalysis:
    """Frozen canonical analysis with detached accessors."""

    _canonical_json: str = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


def analyze_body_sway_continuous_proof(inputs: Any) \
        -> BodySwayContinuousProofAnalysis:
    """Analyze all adjacent preview keys with the fixed proof profile."""

    try:
        from .body_sway_continuous_proof_inputs import (
            BodySwayContinuousProofInputs,
            require_body_sway_continuous_proof_inputs,
        )
        if type(inputs) is not BodySwayContinuousProofInputs:
            raise BodySwayContinuousProofAnalysisError(
                "Continuous analysis requires exact admitted proof inputs"
            )
        admitted = require_body_sway_continuous_proof_inputs(
            inputs.amplitude_candidate, inputs.amplitude_inputs
        )
        return analyze_body_sway_continuous_source(admitted.source)
    except BodySwayContinuousProofAnalysisError:
        raise
    except (
        AttributeError, BodySwayContinuousSourceError, ImportError, KeyError,
        OverflowError, RecursionError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayContinuousProofAnalysisError(
            f"Continuous proof analysis failed: {exc}"
        ) from exc


def analyze_body_sway_continuous_source(
    raw_source: dict[str, Any],
) -> BodySwayContinuousProofAnalysis:
    """Recompute the proof from a complete detached exact source closure."""

    try:
        source = require_body_sway_continuous_source(raw_source)
        candidate = source["amplitude_envelope_candidate"]
        projection = source["preview_projection"]
        timing = candidate["timing"]
        selection = candidate["reviewed_selection"]
        parameters = selection["parameters"]
        motion = source["motion_instance_v2"]
        ticks = projection["sample_ticks"]
        sampler = prepare_body_sway_sampler(
            timing, motion["tracks"], cycles=parameters["cycles"],
            per_bone_amplitude_deg=parameters["per_bone_amplitude_deg"],
            per_bone_phase_fraction=parameters["per_bone_phase_fraction"],
        )
        samples = tuple(sampler.sample(tick) for tick in ticks)
        context = prepare_body_sway_geometry_context(
            source["rig_ir"], source["target_profile"]
        )
        budget_values = body_sway_continuous_proof_budget()
        segments, used_boxes = [], 0
        for left, right in zip(samples, samples[1:]):
            remaining = budget_values["max_total_boxes"] - used_boxes
            if remaining <= 0:
                row = _indeterminate_segment(
                    context, left.tick, right.tick,
                    "global_subdivision_box_budget_exhausted",
                )
            else:
                budget = BodySwayIntervalProofBudget(
                    max_depth=budget_values["max_depth"],
                    max_boxes=min(
                        budget_values["max_boxes_per_segment"], remaining
                    ),
                )
                row = _prove_segment(context, left, right, budget)
            used_boxes += row["evaluated_box_count"]
            if "interval_backend_error" in row["reason_codes"]:
                used_boxes = budget_values["max_total_boxes"]
            segments.append(row)
        certified = bool(segments) and all(
            row["status"] == "continuous_structural_certified"
            for row in segments
        )
        status = "continuous_preview_model_structural_certified" \
            if certified else "indeterminate"
        problem = body_sway_continuous_proof_problem(
            source["source_set_sha256"], list(ticks)
        )
        analysis = {
            "problem": problem,
            "segments": segments,
            "status": status,
            "claims": body_sway_continuous_proof_claims(certified),
            "summary": _summary(segments),
        }
        return BodySwayContinuousProofAnalysis(_canonical(analysis))
    except BodySwayContinuousProofAnalysisError:
        raise
    except (
        AttributeError, BodySwayContinuousSourceError, KeyError,
        OverflowError, RecursionError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayContinuousProofAnalysisError(
            f"Continuous proof analysis failed: {exc}"
        ) from exc


def _prove_segment(context, left, right, budget):
    try:
        proof = prove_body_sway_sampled_linear_segment(
            context, left, right, budget=budget
        )
        row = require_body_sway_interval_backend_result(
            proof, context=context, left_tick=left.tick,
            right_tick=right.tick, budget=budget,
        )
    except (
        ArithmeticError, BodySwayContinuousBackendValidationError,
        BodySwayContinuousIntervalError,
        OverflowError, RuntimeError, TypeError, ValueError,
    ):
        return _indeterminate_segment(
            context, left.tick, right.tick, "interval_backend_error"
        )
    row["segment_evidence_sha256"] = body_sway_continuous_segment_sha256(row)
    return row


def _indeterminate_segment(context, left_tick, right_tick, reason):
    attachment_count = len(context.attachments)
    vertex_count = sum(len(row.setup_vertices_xy)
                       for row in context.attachments)
    meshes = [row for row in context.attachments
              if type(row) is PreparedBodySwayMesh]
    row = {
        "left_tick": left_tick, "right_tick": right_tick,
        "status": "indeterminate", "reason_codes": [reason],
        "bounds": {
            "canvas_margin_lower_px": None,
            "min_signed_area_ratio_lower": None,
            "max_signed_area_ratio_upper": None,
            "max_edge_stretch_squared_ratio_upper": None,
        },
        "evaluated_box_count": 0,
        "certified_terminal_box_count": 0,
        "indeterminate_terminal_box_count": 1,
        "maximum_depth_reached": 0,
        "attachment_count": attachment_count,
        "vertex_count": vertex_count,
        "triangle_count": sum(len(row.deformation.triangles) for row in meshes),
        "edge_count": sum(len(row.deformation.edges) for row in meshes),
        "time_model": "sampled-linear-over-supplied-endpoint-segment",
        "gain_model": "coupled-four-bone-lambda-in-closed-unit-interval",
        "rounding_profile": (
            "binary64-directed-basic-ops-rational-trig-q9-q4096-v1"
        ),
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
    row["segment_evidence_sha256"] = body_sway_continuous_segment_sha256(row)
    return row


def _summary(segments):
    certified = sum(row["status"] == "continuous_structural_certified"
                    for row in segments)
    return {
        "segment_count": len(segments),
        "certified_segment_count": certified,
        "indeterminate_segment_count": len(segments) - certified,
        "evaluated_box_count": sum(row["evaluated_box_count"]
                                   for row in segments),
        "certified_terminal_box_count": sum(
            row["certified_terminal_box_count"] for row in segments
        ),
        "indeterminate_terminal_box_count": sum(
            row["indeterminate_terminal_box_count"] for row in segments
        ),
        "maximum_depth_reached": max(
            (row["maximum_depth_reached"] for row in segments), default=0
        ),
    }


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))
