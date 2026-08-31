"""Shared exact-schedule analysis for authority-free P10.2 remediation."""

from __future__ import annotations

from dataclasses import dataclass

from .body_sway_probe_geometry import (
    BodySwayProbeGeometryError,
    evaluate_prepared_body_sway_geometry_sample,
)
from .body_sway_probe_geometry_context import (
    prepare_body_sway_geometry_context,
)
from .body_sway_probe_inputs import BodySwayProbeInputs
from .body_sway_probe_math import (
    BodySwayProbeMathError,
    build_body_sway_sample_ticks,
)
from .body_sway_probe_report import BodySwayProbeReport
from .body_sway_probe_report_evidence import tick_schedule_sha256
from .body_sway_probe_sampler import prepare_body_sway_sampler
from .dynamic_viewport_fit import (
    DynamicViewportFit,
    DynamicViewportFitError,
    compile_dynamic_viewport_fit,
)
from .region_rebind_candidates import (
    RegionRebindCandidateArtifact,
    RegionRebindCandidateError,
    compile_region_rebind_candidates,
)


class BodySwayRemediationAnalysisError(ValueError):
    """Raised when exact P10.2 evidence cannot form remediation candidates."""


@dataclass(frozen=True, slots=True)
class BodySwayRemediationAnalysis:
    """One shared pose/geometry replay and its detached candidate artifacts."""

    dynamic_viewport: DynamicViewportFit
    rebind_candidates: tuple[RegionRebindCandidateArtifact, ...]


def compile_body_sway_remediation_analysis(
    inputs: BodySwayProbeInputs,
    report: BodySwayProbeReport,
) -> BodySwayRemediationAnalysis:
    """Replay one exact schedule once for viewport and region candidates."""

    try:
        _require_exact_report_binding(inputs, report)
        rig = inputs.rig
        motion = inputs.motion_instance_v2
        parameters = inputs.selection["parameters"]
        sampler = prepare_body_sway_sampler(
            inputs.timing,
            motion["tracks"],
            cycles=parameters["cycles"],
            per_bone_amplitude_deg=parameters["per_bone_amplitude_deg"],
            per_bone_phase_fraction=parameters[
                "per_bone_phase_fraction"
            ],
        )
        ticks = build_body_sway_sample_ticks(
            inputs.timing,
            motion["tracks"],
            cycles=parameters["cycles"],
            per_bone_phase_fraction=parameters[
                "per_bone_phase_fraction"
            ],
        )
        if tick_schedule_sha256(ticks) \
                != report.document["schedule"]["tick_schedule_sha256"]:
            raise BodySwayRemediationAnalysisError(
                "Remediation schedule differs from the reviewed report"
            )
        context = prepare_body_sway_geometry_context(
            rig, inputs.target_profile,
        )
        poses, sampled_geometry, affected_regions = _sample_once(
            ticks, sampler, context,
        )
        canvas = rig["canvas"]
        viewport = compile_dynamic_viewport_fit(
            sampled_geometry=sampled_geometry,
            output_viewport={
                "width": canvas["width"], "height": canvas["height"],
            },
            margin_px=0,
        )
        motion_sha = inputs.source["p9"]["motion_instance_v2_sha256"]
        rebind = tuple(
            compile_region_rebind_candidates(
                rig, poses, project_id=inputs.project_id,
                motion_sha256=motion_sha, attachment_id=attachment_id,
            )
            for attachment_id in sorted(affected_regions)
        )
        return BodySwayRemediationAnalysis(viewport, rebind)
    except BodySwayRemediationAnalysisError:
        raise
    except (
        BodySwayProbeGeometryError, BodySwayProbeMathError,
        DynamicViewportFitError, KeyError, OverflowError,
        RegionRebindCandidateError, TypeError, ValueError,
    ) as exc:
        raise BodySwayRemediationAnalysisError(
            f"Body-sway remediation analysis failed: {exc}"
        ) from exc


def _sample_once(ticks, sampler, context):
    poses, rows, affected = [], [], set()
    for tick in ticks:
        pose = sampler.sample(tick)
        geometry = evaluate_prepared_body_sway_geometry_sample(context, pose)
        poses.append(pose)
        attachments = []
        for item in geometry.attachments:
            attachments.append({
                "attachment_id": item.attachment_id,
                "posed_vertices_xy": [list(point) for point in (
                    item.posed_vertices_xy
                )],
            })
            if item.attachment_type == "region" \
                    and item.canvas_status == "rejected":
                affected.add(item.attachment_id)
        rows.append({"tick": tick, "attachments": attachments})
    return tuple(poses), rows, frozenset(affected)


def _require_exact_report_binding(inputs, report):
    if type(inputs) is not BodySwayProbeInputs \
            or type(report) is not BodySwayProbeReport:
        raise BodySwayRemediationAnalysisError(
            "Remediation analysis requires exact P10.2 inputs and report"
        )
    document = report.document
    expected = {
        "project_id": inputs.project_id,
        "clip_id": inputs.clip_id,
        "source": inputs.source,
        "timing": inputs.timing,
        "selection": inputs.selection,
    }
    if any(document.get(name) != value for name, value in expected.items()):
        raise BodySwayRemediationAnalysisError(
            "Remediation report binding differs from exact P10.2 inputs"
        )
