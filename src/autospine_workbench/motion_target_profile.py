"""Derive immutable P5 retarget metadata from explicit verified P4 and P3 inputs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from typing import Any

from .ik_bundle_contract import build_ik_bundle_contract
from .ik_bundle_integrity import VerifiedIkBundle
from .ik_probe_report import require_ik_probe_report
from .ik_target_geometry import SOURCE_IDENTITY_FIELDS
from .ik_target_profile_validation import require_ik_target_profile
from .mesh_bundle_integrity import VerifiedMeshBundle
from .motion_roles import CANONICAL_IK_HANDLES
from .motion_target_geometry import (
    derive_motion_setup_from_rig_bones,
    quantize,
)
from .motion_target_validation import (
    NUMERIC_PRECISION_DECIMALS,
    PROFILE_FORMAT,
    PROFILE_GENERATOR_ID,
    PROFILE_GENERATOR_VERSION,
    PROFILE_VERSION,
    MotionTargetValidationError,
    require_motion_target_profile,
)
from .resolved_project import canonical_sha256


class MotionTargetProfileError(ValueError):
    """Raised when verified P4/P3 inputs cannot define one P5 target profile."""


@dataclass(frozen=True, slots=True)
class MotionTargetProfile:
    """Frozen canonical target profile with isolated JSON accessors."""

    _document_json: str

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._document_json)

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.document)

    @property
    def bones(self) -> list[dict[str, Any]]:
        return self.document["bones"]

    @property
    def ik_handles(self) -> list[dict[str, Any]]:
        return self.document["ik_handles"]


def compile_motion_target_profile(
    verified_ik: VerifiedIkBundle,
    verified_mesh: VerifiedMeshBundle,
) -> MotionTargetProfile:
    """Project exact P3 setup and exact P4 handles without hidden I/O."""

    try:
        document = _derive_document(verified_ik, verified_mesh)
        require_motion_target_profile(
            document, verified_ik=verified_ik, verified_mesh=verified_mesh
        )
        encoded = json.dumps(
            document, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        )
        return MotionTargetProfile(encoded)
    except MotionTargetProfileError:
        raise
    except (MotionTargetValidationError, KeyError, TypeError, ValueError) as exc:
        raise MotionTargetProfileError(
            f"Motion target profile compilation failed: {exc}"
        ) from exc


def _derive_document(verified_ik, verified_mesh) -> dict[str, Any]:
    profile, p3_source = _require_verified_inputs(verified_ik, verified_mesh)
    rig = verified_mesh.rig
    geometry = derive_motion_setup_from_rig_bones(rig.get("bones"))
    handles = _project_handles(profile)
    if handles != geometry.ik_handles:
        raise MotionTargetProfileError(
            "Verified P4 handles differ from canonical P3 setup"
        )
    mesh_evidence = _project_mesh_evidence(verified_mesh)
    leg_maximums = [
        item["kinematic_reach"]["maximum_px"]
        for item in handles if item["id"] in {"leg.left", "leg.right"}
    ]
    return {
        "format": PROFILE_FORMAT,
        "format_version": PROFILE_VERSION,
        "project_id": verified_ik.project_id,
        "source": {
            "p4_profile_sha256": verified_ik.profile_sha256,
            "p4_probes_sha256": verified_ik.probes_sha256,
            "p4_bundle_sha256": verified_ik.bundle_sha256,
            "p3": p3_source,
        },
        "target_space": {
            "translation": "setup-local-pixel",
            "rotation": "setup-local-degree",
            "scale": "positive-unit-only",
            "canvas": dict(profile["canvas"]),
        },
        "generator": {
            "id": PROFILE_GENERATOR_ID,
            "version": PROFILE_GENERATOR_VERSION,
            "numeric_precision_decimals": NUMERIC_PRECISION_DECIMALS,
        },
        "bones": geometry.bones,
        "ik_handles": handles,
        "body_frame": geometry.body_frame,
        "mesh_evidence": mesh_evidence,
        "reference_length": {
            "value_px": quantize(sum(leg_maximums) / 2.0),
            "method": "mean-leg-maximum-kinematic-reach",
            "handle_ids": ["leg.left", "leg.right"],
        },
    }


def _require_verified_inputs(verified_ik, verified_mesh):
    if not isinstance(verified_ik, VerifiedIkBundle) or \
            not isinstance(verified_mesh, VerifiedMeshBundle):
        raise MotionTargetProfileError(
            "Motion target compilation requires explicit verified P4 and P3 bundles"
        )
    profile, probes = verified_ik.profile, verified_ik.probes
    require_ik_target_profile(profile, verified_bundle=verified_mesh)
    require_ik_probe_report(probes, profile=profile)
    contract = build_ik_bundle_contract(verified_ik.project_id, profile, probes)
    if (
        verified_ik.project_id != verified_mesh.project_id
        or verified_ik.profile_sha256 != contract.profile_sha256
        or verified_ik.probes_sha256 != contract.probes_sha256
        or verified_ik.bundle_sha256 != contract.bundle_sha256
    ):
        raise MotionTargetProfileError("Verified P4 content address is inconsistent")
    source = {field: getattr(verified_mesh, field) for field in SOURCE_IDENTITY_FIELDS}
    if verified_ik.source_identities != source or profile.get("source") != source or \
            verified_ik.p3_rig_sha256 != verified_mesh.rig_sha256 or \
            verified_ik.p3_bundle_sha256 != verified_mesh.bundle_sha256:
        raise MotionTargetProfileError("Verified P4 and P3 identity chains differ")
    return profile, source


def _project_handles(profile):
    raw = profile.get("handles")
    if not isinstance(raw, list) or [item.get("id") for item in raw] != list(CANONICAL_IK_HANDLES):
        raise MotionTargetProfileError("Verified P4 handle inventory is invalid")
    return json.loads(json.dumps(raw, allow_nan=False))


def _project_mesh_evidence(verified_mesh):
    rig, probes, visuals = (
        verified_mesh.rig, verified_mesh.probes, verified_mesh.visuals
    )
    rig_qa = rig.get("qa") if isinstance(rig, Mapping) else None
    targets = visuals.get("targets") if isinstance(visuals, Mapping) else None
    summary = visuals.get("summary") if isinstance(visuals, Mapping) else None
    if not isinstance(targets, list) or not isinstance(summary, str):
        raise MotionTargetProfileError("Verified P3 mesh evidence is invalid")
    expected_summary = "reviewed-noop" if not targets else f"converted={len(targets)}"
    if summary != expected_summary:
        raise MotionTargetProfileError("Verified P3 mesh evidence summary differs")
    return {
        "status": "reviewed-noop" if not targets else "converted",
        "summary": summary,
        "rig_qa_status": (rig_qa or {}).get("status"),
        "probes_status": probes.get("status") if isinstance(probes, Mapping) else None,
        "visuals_status": visuals.get("status"),
        "target_inventory": json.loads(json.dumps(targets, allow_nan=False)),
    }
