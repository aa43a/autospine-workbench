"""Pure compiler for one reviewed BodySwayProbeReport v1."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .body_sway_probe_geometry import (
    BodySwayProbeGeometryError,
    evaluate_prepared_body_sway_geometry_sample,
)
from .body_sway_probe_geometry_context import (
    prepare_body_sway_geometry_context,
)
from .body_sway_probe_inputs import BodySwayProbeInputs
from .body_sway_probe_math import (
    BodySwayPoseSample,
    audit_body_sway_loop,
    build_body_sway_sample_ticks,
)
from .body_sway_probe_math_inputs import BodySwayProbeMathError
from .body_sway_probe_profile import MAX_SAMPLE_COUNT, body_sway_probe_profile
from .body_sway_probe_sampler import prepare_body_sway_sampler
from .body_sway_probe_report_evidence import (
    BodySwayProbeReportEvidenceError,
    SampleStreamSealer,
    StructuralEvidenceAccumulator,
    tick_schedule_sha256,
)
from .body_sway_probe_sample_validation import (
    MAX_REPRESENTATIVE_SAMPLES,
    representative_sample_sha256,
)
from .body_sway_probe_validation import (
    FORMAT,
    FORMAT_VERSION,
    SEMANTICS,
    BodySwayProbeValidationError,
    body_sway_probe_report_sha256,
    require_body_sway_probe_report,
)
from .resolved_project import canonical_sha256


ENDPOINT_POSE_HASH_DOMAIN = "autospine-body-sway-endpoint-pose-state/v1"


class BodySwayProbeReportError(ValueError):
    """Raised when admitted inputs cannot produce complete probe evidence."""


@dataclass(frozen=True, slots=True)
class BodySwayProbeReport:
    """Frozen canonical report; accessors always return detached values."""

    _canonical_json: str

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


def compile_body_sway_probe_report(
    inputs: BodySwayProbeInputs,
) -> BodySwayProbeReport:
    """Sample exact P3/P5/P9 evidence; never emit a timeline or safety claim."""

    if type(inputs) is not BodySwayProbeInputs:
        raise BodySwayProbeReportError(
            "Body-sway report compilation requires exact admitted inputs"
        )
    try:
        rig = inputs.rig
        target = inputs.target_profile
        motion = inputs.motion_instance_v2
        timing = inputs.timing
        selection = inputs.selection
        parameters = selection["parameters"]
        tracks = motion["tracks"]
        sampler = prepare_body_sway_sampler(
            timing,
            tracks,
            cycles=parameters["cycles"],
            per_bone_amplitude_deg=parameters["per_bone_amplitude_deg"],
            per_bone_phase_fraction=parameters["per_bone_phase_fraction"],
        )
        geometry_context = prepare_body_sway_geometry_context(rig, target)
        ticks = build_body_sway_sample_ticks(
            timing, tracks, cycles=parameters["cycles"],
            per_bone_phase_fraction=parameters["per_bone_phase_fraction"],
        )
        representative_indices = select_representative_indices(len(ticks))
        rig_bone_ids = tuple(sorted(row["id"] for row in rig["bones"]))
        overlay_bone_ids = tuple(
            row["bone_id"] for row in parameters["per_bone_amplitude_deg"]
        )
        rotation_bone_ids = _rotation_inventory(tracks, overlay_bone_ids)
        attachments = tuple(sorted(
            (row["id"], row["type"]) for row in rig["attachments"]
        ))
        stream = SampleStreamSealer(
            rig_bone_ids=rig_bone_ids,
            rotation_bone_ids=rotation_bone_ids,
            overlay_bone_ids=overlay_bone_ids,
            attachments=attachments,
        )
        structural = StructuralEvidenceAccumulator(
            rig_bone_ids=rig_bone_ids, attachments=attachments,
        )
        representatives: list[dict[str, Any]] = []
        selected = set(representative_indices)
        start = end = None
        start_pose_sha = end_pose_sha = None
        for index, tick in enumerate(ticks):
            sample = sampler.sample(tick)
            visible = _visible_sample(sample, rotation_bone_ids)
            pose_sha = visible["sample_sha256"]
            stream.observe(tick, pose_sha)
            if index in selected:
                representatives.append(visible)
            if index == 0:
                start = sample
                start_pose_sha = _endpoint_pose_state_sha256(visible)
            if index == len(ticks) - 1:
                end = sample
                end_pose_sha = _endpoint_pose_state_sha256(visible)
            structural.observe(
                evaluate_prepared_body_sway_geometry_sample(
                    geometry_context, sample
                )
            )
        if start is None or end is None \
                or start_pose_sha is None or end_pose_sha is None:
            raise BodySwayProbeReportError("Body-sway schedule produced no samples")
        audit = audit_body_sway_loop(timing, start, end)
        checks = structural.checks(
            loop_audit=audit, start_pose_state_sha256=start_pose_sha,
            end_pose_state_sha256=end_pose_sha,
            expected_sample_count=len(ticks),
        )
        document = _document(
            inputs, ticks=ticks, rotation_bone_ids=rotation_bone_ids,
            overlay_bone_ids=overlay_bone_ids, rig_bone_ids=rig_bone_ids,
            attachments=attachments, representatives=representatives,
            sample_stream_sha256=stream.finish(len(ticks)), checks=checks,
        )
        require_body_sway_probe_report(document)
        value = BodySwayProbeReport(_canonical(document))
        if value.sha256 != body_sway_probe_report_sha256(value.document):
            raise BodySwayProbeReportError(
                "Body-sway report canonical identity is inconsistent"
            )
        return value
    except BodySwayProbeReportError:
        raise
    except (
        BodySwayProbeGeometryError, BodySwayProbeMathError,
        BodySwayProbeReportEvidenceError, BodySwayProbeValidationError,
        KeyError, OverflowError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayProbeReportError(
            f"Body-sway report compilation failed: {exc}"
        ) from exc


def select_representative_indices(sample_count: int) -> tuple[int, ...]:
    """Select at most 256 uniformly indexed rows, always including endpoints."""

    if type(sample_count) is not int or not 2 <= sample_count <= MAX_SAMPLE_COUNT:
        raise BodySwayProbeReportError("Body-sway sample count is invalid")
    if sample_count <= MAX_REPRESENTATIVE_SAMPLES:
        return tuple(range(sample_count))
    last = sample_count - 1
    count = MAX_REPRESENTATIVE_SAMPLES
    return tuple(index * last // (count - 1) for index in range(count))


def _visible_sample(
    sample: BodySwayPoseSample, rotation_bone_ids: tuple[str, ...],
) -> dict[str, Any]:
    base = dict(sample.base_rotation_deg)
    overlay = dict(sample.overlay_rotation_deg)
    combined = dict(sample.combined_rotation_deg)
    if tuple(sorted(base)) != rotation_bone_ids \
            or tuple(sorted(combined)) != rotation_bone_ids \
            or not set(overlay) <= set(rotation_bone_ids):
        raise BodySwayProbeReportError(
            "Sample rotation inventory differs from its admitted tracks"
        )
    row = {
        "tick": sample.tick,
        "base_rotation_deg": _rotation_rows(rotation_bone_ids, base),
        "overlay_rotation_deg": _rotation_rows(rotation_bone_ids, overlay),
        "combined_rotation_deg": _rotation_rows(rotation_bone_ids, combined),
        "root_translation_xy": list(sample.root_translation_xy),
    }
    row["sample_sha256"] = representative_sample_sha256(row)
    return row


def _endpoint_pose_state_sha256(row: dict[str, Any]) -> str:
    return canonical_sha256({
        "domain": ENDPOINT_POSE_HASH_DOMAIN,
        "base_rotation_deg": row["base_rotation_deg"],
        "overlay_rotation_deg": row["overlay_rotation_deg"],
        "combined_rotation_deg": row["combined_rotation_deg"],
        "root_translation_xy": row["root_translation_xy"],
    })


def _document(
    inputs, *, ticks, rotation_bone_ids, overlay_bone_ids, rig_bone_ids,
    attachments, representatives, sample_stream_sha256, checks,
):
    counts = {name: sum(row["status"] == name for row in checks)
              for name in ("passed", "rejected", "unobservable", "not_applicable")}
    rejected = any(
        row["check_id"] in {
            "loop_closure", "fk_finite", "sampled_mesh_deformation",
            "sampled_canvas_containment", "shared_index_internal_continuity",
        } and row["status"] == "rejected"
        for row in checks
    )
    reasons = [
        "manual_runtime_preview_required", "reviewed_seam_anchors_missing",
        "safe_range_unproven",
    ]
    if rejected:
        reasons.append("sampled_structural_check_rejected")
    mesh_count = sum(kind == "mesh" for _identifier, kind in attachments)
    return {
        "format": FORMAT, "format_version": FORMAT_VERSION,
        "project_id": inputs.project_id, "clip_id": inputs.clip_id,
        "source": inputs.source, "timing": inputs.timing,
        "selection": inputs.selection, "prober": body_sway_probe_profile(),
        "semantics": _copy(SEMANTICS),
        "schedule": {
            "tick_schedule_sha256": tick_schedule_sha256(ticks),
            "sample_count": len(ticks), "first_tick": ticks[0],
            "last_tick": ticks[-1],
        },
        "sample_stream": {
            "sample_stream_sha256": sample_stream_sha256,
            "rig_bone_ids": list(rig_bone_ids),
            "rotation_bone_ids": list(rotation_bone_ids),
            "overlay_bone_ids": list(overlay_bone_ids),
            "attachments": [
                {"attachment_id": identifier, "type": kind}
                for identifier, kind in attachments
            ],
            "representative_samples": representatives,
        },
        "checks": checks,
        "status": "structural_rejected" if rejected else "manual_visual_required",
        "release_gate": {"status": "blocked", "reason_codes": sorted(reasons)},
        "summary": {
            "schedule_sample_count": len(ticks),
            "representative_sample_count": len(representatives),
            "rig_bone_count": len(rig_bone_ids),
            "rotation_bone_count": len(rotation_bone_ids),
            "overlay_bone_count": len(overlay_bone_ids),
            "attachment_count": len(attachments),
            "mesh_attachment_count": mesh_count, "check_count": len(checks),
            **{f"{name}_check_count": count for name, count in counts.items()},
        },
    }


def _rotation_inventory(tracks, overlay_bone_ids):
    return tuple(sorted({
        row["bone_id"] for row in tracks if row["property"] == "rotation"
    } | set(overlay_bone_ids)))


def _rotation_rows(inventory, values):
    return [{"bone_id": bone_id, "value": values.get(bone_id, 0.0)}
            for bone_id in inventory]


def _copy(value: Any) -> Any:
    return json.loads(_canonical(value))


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))
