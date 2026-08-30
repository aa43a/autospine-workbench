"""Bounded, non-authoritative visual witnesses for one exact P10.2 report."""

from __future__ import annotations

from typing import Any

from .body_sway_probe_geometry import (
    BodySwayProbeGeometryError,
    evaluate_prepared_body_sway_geometry_sample,
)
from .body_sway_probe_geometry_context import (
    prepare_body_sway_geometry_context,
)
from .body_sway_probe_inputs import BodySwayProbeInputs
from .body_sway_probe_math_inputs import BodySwayProbeMathError
from .body_sway_probe_report import BodySwayProbeReport
from .body_sway_probe_sampler import prepare_body_sway_sampler
from .body_sway_probe_validation import (
    BodySwayProbeValidationError,
    require_body_sway_probe_report,
)
from .idle_behavior_review_profile import TARGET_BONE_IDS


MAX_WITNESSES = 9
MAX_CANVAS_FAILURE_MARKERS = 16


class BodySwayProbePreviewError(ValueError):
    """Raised when bounded witnesses differ from exact report evidence."""


def build_body_sway_probe_preview(
    inputs: BodySwayProbeInputs,
    report: BodySwayProbeReport,
) -> dict[str, Any]:
    """Recompute at most nine report representatives for operator display."""

    if type(inputs) is not BodySwayProbeInputs \
            or type(report) is not BodySwayProbeReport:
        raise BodySwayProbePreviewError(
            "Body-sway preview requires exact admitted values"
        )
    try:
        document = report.document
        require_body_sway_probe_report(document)
        _require_source(inputs, document)
        representatives = document["sample_stream"]["representative_samples"]
        rows = [representatives[index]
                for index in _indices(len(representatives))]
        parameters = inputs.selection["parameters"]
        motion = inputs.motion_instance_v2
        sampler = prepare_body_sway_sampler(
            inputs.timing, motion["tracks"], cycles=parameters["cycles"],
            per_bone_amplitude_deg=parameters["per_bone_amplitude_deg"],
            per_bone_phase_fraction=parameters["per_bone_phase_fraction"],
        )
        geometry = prepare_body_sway_geometry_context(
            inputs.rig, inputs.target_profile,
        )
        witnesses = []
        for row in rows:
            sample = sampler.sample(row["tick"])
            _require_visible_pose(sample, row)
            posed = evaluate_prepared_body_sway_geometry_sample(
                geometry, sample,
            )
            witnesses.append(_witness(posed))
        return {
            "kind": "sampled-structural-witness-preview",
            "authority": "none",
            "scope": "sampled-diagnostic-only",
            "canonical_checks_are_authoritative": True,
            "witnesses_are_exhaustive": False,
            "timing": inputs.timing,
            "representative_sample_count": len(representatives),
            "witness_count": len(witnesses),
            "witnesses_truncated": len(witnesses) < len(representatives),
            "canvas_failure_marker_limit": MAX_CANVAS_FAILURE_MARKERS,
            "witnesses": witnesses,
        }
    except BodySwayProbePreviewError:
        raise
    except (
        BodySwayProbeGeometryError, BodySwayProbeMathError,
        BodySwayProbeValidationError, KeyError, OverflowError,
        TypeError, ValueError,
    ) as exc:
        raise BodySwayProbePreviewError(
            "Body-sway witness preview could not be reproduced"
        ) from exc


def _indices(count: int) -> tuple[int, ...]:
    if type(count) is not int or count < 2:
        raise BodySwayProbePreviewError(
            "Body-sway representative inventory is invalid"
        )
    if count <= MAX_WITNESSES:
        return tuple(range(count))
    last = count - 1
    return tuple(
        index * last // (MAX_WITNESSES - 1)
        for index in range(MAX_WITNESSES)
    )


def _require_source(inputs, report) -> None:
    source = report["source"]
    if source != inputs.source \
            or report["selection"] != inputs.selection \
            or report["project_id"] != inputs.project_id \
            or report["clip_id"] != inputs.clip_id:
        raise BodySwayProbePreviewError(
            "Body-sway report differs from its admitted inputs"
        )


def _require_visible_pose(sample, row) -> None:
    for field, values in (
        ("base_rotation_deg", sample.base_rotation_deg),
        ("overlay_rotation_deg", sample.overlay_rotation_deg),
        ("combined_rotation_deg", sample.combined_rotation_deg),
    ):
        expected = dict(values)
        if any(item["value"] != expected.get(item["bone_id"], 0.0)
               for item in row[field]):
            raise BodySwayProbePreviewError(
                "Body-sway witness pose differs from the canonical report"
            )
    if row["root_translation_xy"] != list(sample.root_translation_xy):
        raise BodySwayProbePreviewError(
            "Body-sway witness root differs from the canonical report"
        )


def _witness(geometry) -> dict[str, Any]:
    bones = {row.bone_id: row for row in geometry.bones}
    if not set(TARGET_BONE_IDS) <= set(bones):
        raise BodySwayProbePreviewError(
            "Body-sway witness target bone inventory is incomplete"
        )
    failures = geometry.canvas_failures
    markers = [
        {
            "attachment_id": row.attachment_id,
            "vertex_index": row.vertex_index,
            "point_xy": list(row.point_xy),
            "sides": list(row.sides),
        }
        for row in failures[:MAX_CANVAS_FAILURE_MARKERS]
    ]
    return {
        "tick": geometry.tick,
        "status": geometry.status,
        "target_bones": [
            {
                "bone_id": bone_id,
                "start_xy": list(bones[bone_id].origin_xy),
                "end_xy": list(bones[bone_id].endpoint_xy),
                "rotation_deg": bones[bone_id].rotation_deg,
            }
            for bone_id in TARGET_BONE_IDS
        ],
        "canvas_failure_count": len(failures),
        "canvas_failure_markers": markers,
        "canvas_failure_markers_truncated": len(markers) < len(failures),
    }
