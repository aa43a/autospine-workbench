"""Clip-specific P3 mesh deformation regression for retargeted MotionInstance."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from typing import Any

from .ik_probe_math import quantize
from .ik_target_geometry import SOURCE_IDENTITY_FIELDS
from .mesh_action_probe import MAX_AREA_RATIO, MAX_EDGE_STRETCH, MIN_AREA_RATIO
from .mesh_action_probe_inputs import ActionProbeInputError, normalize_probe_input
from .mesh_bundle_integrity import VerifiedMeshBundle
from .mesh_deformation_metrics import DeformationMetricsError, measure_deformation
from .mesh_skinning import MeshSkinningError, skin_vertices_lbs
from .motion_instance_sampling import (
    SAMPLE_STEP_TICKS,
    instance_sample_ticks,
    sample_instance_deltas,
)
from .motion_instance_validation import instance_sha256, require_motion_instance
from .motion_target_validation import require_motion_target_profile
from .resolved_project import canonical_sha256


FORMAT = "autospine-motion-mesh-regression"
FORMAT_VERSION = 1


class MotionMeshRegressionError(ValueError):
    """Raised when exact P3 mesh evidence cannot be evaluated for a clip."""


@dataclass(frozen=True, slots=True)
class MotionMeshRegression:
    """Frozen canonical report with isolated document access."""

    _document_json: str

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._document_json)

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.document)


def build_motion_mesh_regression(
    instance: Mapping[str, Any],
    target_profile: Mapping[str, Any],
    verified_mesh: VerifiedMeshBundle,
) -> MotionMeshRegression:
    """Sample one exact instance and reject any unsafe converted P3 mesh pose."""

    try:
        require_motion_instance(instance, target_profile=target_profile)
        require_motion_target_profile(target_profile)
        rig, targets = _verified_inputs(target_profile, verified_mesh)
        ticks = instance_sample_ticks(instance, target_profile=target_profile)
        attachments = _attachments(rig, targets)
        entries = [
            _probe_attachment(instance, target_profile, rig["bones"], item,
                              attachments[item["attachment_id"]], ticks)
            for item in targets
        ]
        status = "rejected" if any(
            item["status"] == "rejected" for item in entries
        ) else "passed"
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "clip_id": instance["clip_id"],
            "source": {
                "instance_sha256": instance_sha256(instance),
                "target_profile_sha256": canonical_sha256(target_profile),
                "p3_rig_sha256": verified_mesh.rig_sha256,
                "p3_bundle_sha256": verified_mesh.bundle_sha256,
            },
            "prober": {
                "id": "motion-mesh-regression",
                "version": "1.0.0",
                "config": {
                    "sample_step_ticks": SAMPLE_STEP_TICKS,
                    "min_area_ratio": MIN_AREA_RATIO,
                    "max_area_ratio": MAX_AREA_RATIO,
                    "max_edge_stretch": MAX_EDGE_STRETCH,
                    "root_translation_deformation_invariant": True,
                },
            },
            "status": status,
            "summary": f"attachments={len(entries)}" if entries else "reviewed-noop",
            "sample_count": len(ticks),
            "attachments": entries,
        }
        encoded = _encode(document)
        return MotionMeshRegression(encoded)
    except MotionMeshRegressionError:
        raise
    except (
        ActionProbeInputError,
        DeformationMetricsError,
        MeshSkinningError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise MotionMeshRegressionError(
            f"Motion mesh regression failed: {exc}"
        ) from exc


def require_motion_mesh_regression(
    document: Mapping[str, Any],
    *,
    instance: Mapping[str, Any],
    target_profile: Mapping[str, Any],
    verified_mesh: VerifiedMeshBundle,
) -> None:
    """Rebuild the complete regression and require canonical equality."""

    if not isinstance(document, Mapping):
        raise MotionMeshRegressionError("Motion mesh regression must be an object")
    expected = build_motion_mesh_regression(
        instance, target_profile, verified_mesh
    ).document
    try:
        if canonical_sha256(document) != canonical_sha256(expected):
            raise MotionMeshRegressionError(
                "Motion mesh regression differs from recomputed evidence"
            )
    except (TypeError, ValueError) as exc:
        raise MotionMeshRegressionError(
            "Motion mesh regression is not canonical JSON"
        ) from exc


def _verified_inputs(target, mesh):
    if type(mesh) is not VerifiedMeshBundle:
        raise MotionMeshRegressionError(
            "Motion mesh regression requires an exact VerifiedMeshBundle"
        )
    source = target["source"]["p3"]
    expected = {field: getattr(mesh, field) for field in SOURCE_IDENTITY_FIELDS}
    if target["project_id"] != mesh.project_id or source != expected:
        raise MotionMeshRegressionError("Motion target and P3 identity chains differ")
    documents = {
        "rig_sha256": mesh.rig,
        "run_sha256": mesh.run_manifest,
        "probes_sha256": mesh.probes,
        "visuals_sha256": mesh.visuals,
    }
    if any(canonical_sha256(value) != getattr(mesh, field)
           for field, value in documents.items()):
        raise MotionMeshRegressionError("Verified P3 document identity differs")
    targets = target["mesh_evidence"]["target_inventory"]
    visuals = mesh.visuals
    if visuals.get("targets") != targets or visuals.get("status") != "passed" \
            or mesh.probes.get("status") != "passed":
        raise MotionMeshRegressionError("Verified P3 mesh evidence differs")
    return mesh.rig, targets


def _attachments(rig, targets):
    rows = rig.get("attachments")
    if not isinstance(rows, list):
        raise MotionMeshRegressionError("P3 attachment inventory is invalid")
    indexed = {
        item.get("id"): item for item in rows
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
    }
    expected = {item["attachment_id"] for item in targets}
    if len(indexed) != len(rows) or any(
        identifier not in indexed or indexed[identifier].get("type") != "mesh"
        for identifier in expected
    ):
        raise MotionMeshRegressionError("P3 mesh target attachment is missing")
    actual_mesh = {
        identifier for identifier, item in indexed.items()
        if item.get("type") == "mesh"
    }
    if actual_mesh != expected:
        raise MotionMeshRegressionError("P3 mesh inventory differs from targets")
    return indexed


def _probe_attachment(instance, target, bones, target_row, attachment, ticks):
    normalized = normalize_probe_input(
        bones, attachment,
        target_row["proximal_bone_id"], target_row["distal_bone_id"],
    )
    assessments = []
    for tick in ticks:
        rotations, _translation = sample_instance_deltas(
            instance, target_profile=target, tick=tick
        )
        posed = skin_vertices_lbs(
            normalized.rig_bones, normalized.vertices_xy,
            normalized.weights, rotations,
        )
        assessments.append((tick, measure_deformation(
            normalized.vertices_xy, posed, normalized.triangles,
            min_area_ratio=MIN_AREA_RATIO,
            max_area_ratio=MAX_AREA_RATIO,
            max_edge_stretch=MAX_EDGE_STRETCH,
        )))
    failed = [tick for tick, item in assessments if item.status != "passed"]
    metrics = [item.metrics for _tick, item in assessments]
    return {
        **{field: target_row[field] for field in (
            "attachment_id", "source_layer_id", "side",
            "proximal_bone_id", "distal_bone_id",
        )},
        "status": "rejected" if failed else "passed",
        "failed_tick_count": len(failed),
        "first_failure_tick": failed[0] if failed else None,
        "worst": {
            "max_flipped_count": max(item.flipped_count for item in metrics),
            "max_degenerate_count": max(item.degenerate_count for item in metrics),
            "min_signed_area_ratio": quantize(min(
                item.min_signed_area_ratio for item in metrics
                if item.min_signed_area_ratio is not None
            )),
            "max_signed_area_ratio": quantize(max(
                item.max_signed_area_ratio for item in metrics
                if item.max_signed_area_ratio is not None
            )),
            "max_edge_stretch_ratio": quantize(max(
                item.max_edge_stretch_ratio for item in metrics
                if item.max_edge_stretch_ratio is not None
            )),
            "max_interior_crack_gap_px": quantize(max(
                item.interior_crack_gap_px for item in metrics
            )),
        },
    }


def _encode(value):
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
