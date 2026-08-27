"""Exact detached source closure for P10.4b2 continuous proofs."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .body_sway_amplitude_envelope_validation import (
    body_sway_amplitude_envelope_candidate_sha256,
    require_body_sway_amplitude_envelope_candidate,
)
from .body_sway_continuous_proof_profile import (
    MAX_PREVIEW_PROJECTION_BYTES,
    MAX_RIG_IR_BYTES,
    MAX_TARGET_PROFILE_BYTES,
    body_sway_continuous_source_sha256,
)
from .body_sway_amplitude_envelope_profile import MAX_ENVELOPE_DOCUMENT_BYTES
from .body_sway_preview_projection import (
    body_sway_preview_base_animation_sha256,
    body_sway_preview_setup_sha256,
    build_body_sway_preview_projection_document,
)
from .body_sway_probe_geometry_context import (
    prepare_body_sway_geometry_context,
)
from .body_sway_probe_math import build_body_sway_sample_ticks
from .body_sway_probe_report_evidence import tick_schedule_sha256
from .body_sway_probe_sampler import prepare_body_sway_sampler
from .motion_instance_v2_validation import (
    MAX_DOCUMENT_BYTES as MAX_MOTION_INSTANCE_V2_BYTES,
    motion_instance_v2_sha256,
    require_motion_instance_v2,
)
from .motion_target_validation import require_motion_target_profile
from .resolved_project import canonical_sha256
from .spine42_json_adapter import build_spine42_json
from .spine42_timeline_projection import project_spine42_motion
from .temporary_body_sway_preview_validation import (
    MAX_DOCUMENT_BYTES as MAX_TEMPORARY_PREVIEW_BYTES,
    require_temporary_body_sway_preview_manifest,
)


class BodySwayContinuousSourceError(ValueError):
    """Raised when any embedded proof source can be detached or cross-wired."""


def build_body_sway_continuous_source(
    *,
    amplitude_candidate: Mapping[str, Any],
    rig: Mapping[str, Any],
    target_profile: Mapping[str, Any],
    motion_instance_v2: Mapping[str, Any],
    temporary_preview_manifest: Mapping[str, Any],
    preview_projection: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate every snapshot, rebuild projection, and seal one source set."""

    try:
        candidate = _copy_object(amplitude_candidate, "amplitude candidate")
        rig_doc = _copy_object(rig, "RigIR")
        target = _copy_object(target_profile, "target profile")
        motion = _copy_object(motion_instance_v2, "MotionInstance v2")
        manifest = _copy_object(
            temporary_preview_manifest, "temporary preview manifest"
        )
        projection = _copy_object(preview_projection, "preview projection")
        _require_document_budgets(
            candidate, rig_doc, target, motion, manifest, projection
        )
        require_body_sway_amplitude_envelope_candidate(candidate)
        prepare_body_sway_geometry_context(rig_doc, target)
        require_motion_target_profile(target)
        require_motion_instance_v2(motion, target_profile=target)
        require_temporary_body_sway_preview_manifest(manifest)
        expected_projection = _rebuild_projection(
            candidate, rig_doc, motion
        )
        if _canonical(projection) != _canonical(expected_projection):
            raise BodySwayContinuousSourceError(
                "Continuous proof projection differs from exact source replay"
            )
        identities = _identities(
            candidate, rig_doc, target, motion, manifest, projection
        )
        _require_cross_chain(
            candidate, rig_doc, target, motion, manifest,
            projection, identities,
        )
        source = {
            "amplitude_envelope_candidate_sha256": identities["candidate"],
            "amplitude_envelope_candidate": candidate,
            "rig_ir_sha256": identities["rig"],
            "rig_ir": rig_doc,
            "target_profile_sha256": identities["target"],
            "target_profile": target,
            "motion_instance_v2_sha256": identities["motion"],
            "motion_instance_v2": motion,
            "temporary_preview_manifest_sha256": identities["manifest"],
            "temporary_preview_manifest": manifest,
            "preview_projection_sha256": identities["projection"],
            "preview_projection": projection,
        }
        source["source_set_sha256"] = body_sway_continuous_source_sha256(
            source
        )
        return source
    except BodySwayContinuousSourceError:
        raise
    except (
        AttributeError, KeyError, OverflowError, RecursionError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayContinuousSourceError(
            f"Continuous proof source admission failed: {exc}"
        ) from exc


def require_body_sway_continuous_source(
    source: Mapping[str, Any],
) -> dict[str, Any]:
    """Rebuild a supplied detached source and require byte identity."""

    raw = _copy_object(source, "continuous proof source")
    required = {
        "source_set_sha256", "amplitude_envelope_candidate_sha256",
        "amplitude_envelope_candidate", "rig_ir_sha256", "rig_ir",
        "target_profile_sha256", "target_profile",
        "motion_instance_v2_sha256", "motion_instance_v2",
        "temporary_preview_manifest_sha256", "temporary_preview_manifest",
        "preview_projection_sha256", "preview_projection",
    }
    if set(raw) != required:
        raise BodySwayContinuousSourceError(
            "Continuous proof source fields are unsupported"
        )
    rebuilt = build_body_sway_continuous_source(
        amplitude_candidate=raw["amplitude_envelope_candidate"],
        rig=raw["rig_ir"], target_profile=raw["target_profile"],
        motion_instance_v2=raw["motion_instance_v2"],
        temporary_preview_manifest=raw["temporary_preview_manifest"],
        preview_projection=raw["preview_projection"],
    )
    if _canonical(raw) != _canonical(rebuilt):
        raise BodySwayContinuousSourceError(
            "Continuous proof source identities differ from exact replay"
        )
    return rebuilt


def _rebuild_projection(candidate, rig, motion):
    report = candidate["source"]["reviewed_probe_report"]
    timing, selection = candidate["timing"], candidate["reviewed_selection"]
    parameters = selection["parameters"]
    ticks = build_body_sway_sample_ticks(
        timing, motion["tracks"], cycles=parameters["cycles"],
        per_bone_phase_fraction=parameters["per_bone_phase_fraction"],
    )
    sampler = prepare_body_sway_sampler(
        timing, motion["tracks"], cycles=parameters["cycles"],
        per_bone_amplitude_deg=parameters["per_bone_amplitude_deg"],
        per_bone_phase_fraction=parameters["per_bone_phase_fraction"],
    )
    inventory = tuple(report["sample_stream"]["rotation_bone_ids"])
    keys = {bone_id: [] for bone_id in inventory}
    for tick in ticks:
        combined = dict(sampler.sample(tick).combined_rotation_deg)
        if tuple(sorted(combined)) != inventory:
            raise BodySwayContinuousSourceError(
                "Continuous proof rotation inventory differs from P10.2"
            )
        for bone_id in inventory:
            keys[bone_id].append({"tick": tick, "value": combined[bone_id]})
    tracks = [
        {"bone_id": bone_id, "property": "rotation", "keys": keys[bone_id]}
        for bone_id in inventory
    ]
    setup = build_spine42_json(rig)
    slots = [
        {"name": row["id"]} for row in sorted(
            rig["slots"], key=lambda row: (row["setup_draw_order"], row["id"])
        )
    ]
    _events, base_animation = project_spine42_motion(motion, slots)
    return build_body_sway_preview_projection_document(
        project_id=candidate["project_id"], clip_id=candidate["clip_id"],
        report_sha256=candidate["source"]["review_admission"]["source"]
            ["p10_chain"]["body_sway_probe_report_sha256"],
        base_motion_instance_v2_sha256=motion_instance_v2_sha256(motion),
        base_animation_sha256=body_sway_preview_base_animation_sha256(
            base_animation
        ),
        setup_sha256=body_sway_preview_setup_sha256(setup),
        timing=timing, selection=selection,
        tick_schedule_sha256_value=tick_schedule_sha256(tuple(ticks)),
        sample_stream_sha256=report["sample_stream"]["sample_stream_sha256"],
        sample_ticks=list(ticks), rotation_tracks=tracks,
    )


def _identities(candidate, rig, target, motion, manifest, projection):
    return {
        "candidate": body_sway_amplitude_envelope_candidate_sha256(candidate),
        "rig": canonical_sha256(rig), "target": canonical_sha256(target),
        "motion": motion_instance_v2_sha256(motion),
        "manifest": canonical_sha256(manifest),
        "projection": canonical_sha256(projection),
    }


def _require_document_budgets(candidate, rig, target, motion,
                              manifest, projection):
    limits = (
        (candidate, MAX_ENVELOPE_DOCUMENT_BYTES, "amplitude candidate"),
        (rig, MAX_RIG_IR_BYTES, "RigIR"),
        (target, MAX_TARGET_PROFILE_BYTES, "target profile"),
        (motion, MAX_MOTION_INSTANCE_V2_BYTES, "MotionInstance v2"),
        (manifest, MAX_TEMPORARY_PREVIEW_BYTES, "temporary preview"),
        (projection, MAX_PREVIEW_PROJECTION_BYTES, "preview projection"),
    )
    for document, limit, label in limits:
        if len(_canonical(document).encode("utf-8")) > limit:
            raise BodySwayContinuousSourceError(
                f"Continuous proof {label} exceeds its byte limit"
            )


def _require_cross_chain(candidate, rig, target, motion, manifest,
                         projection, identities):
    report = candidate["source"]["reviewed_probe_report"]
    admission = candidate["source"]["review_admission"]
    capture = admission["source"]["capture"]
    if candidate["project_id"] != target["project_id"] \
            or candidate["project_id"] != manifest["project_id"] \
            or candidate["clip_id"] != motion["clip_id"] \
            or candidate["clip_id"] != manifest["clip_id"] \
            or candidate["timing"] != motion["timing"] \
            or candidate["timing"] != manifest["timing"] \
            or candidate["reviewed_selection"] != manifest["selection"]:
        raise BodySwayContinuousSourceError(
            "Continuous proof source project, clip, timing, or selection differs"
        )
    if identities["rig"] != report["source"]["p3"]["rig_sha256"] \
            or identities["target"] \
                != report["source"]["p5"]["target_profile_sha256"] \
            or identities["motion"] \
                != report["source"]["p9"]["motion_instance_v2_sha256"] \
            or identities["manifest"] \
                != capture["temporary_preview_sha256"] \
            or manifest["artifacts"]["artifact_set_sha256"] \
                != capture["preview_artifact_set_sha256"] \
            or identities["projection"] \
                != manifest["projection"]["projection_sha256"]:
        raise BodySwayContinuousSourceError(
            "Continuous proof source digests differ from embedded upstream chain"
        )
    if projection["project_id"] != candidate["project_id"] \
            or projection["clip_id"] != candidate["clip_id"]:
        raise BodySwayContinuousSourceError(
            "Continuous proof projection identity is cross-wired"
        )


def _copy_object(value: Any, label: str) -> dict[str, Any]:
    copied = json.loads(_canonical(value))
    if not isinstance(copied, dict):
        raise BodySwayContinuousSourceError(f"{label} must be a JSON object")
    return copied


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))
