"""Compile target-rig length candidates from verified projection evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any

from .motion_target_validation import (
    MotionTargetValidationError,
    require_motion_target_profile,
)
from .projected_motion_bundle_contract import (
    ProjectedMotionBundleContractError,
    build_projected_motion_bundle_contract,
)
from .projected_motion_bundle_integrity import VerifiedProjectedMotionBundle
from .projected_motion_geometry_validation import ProjectedMotionValidationError
from .projected_motion_validation import require_projected_motion_ir
from .projected_scale_probe_validation import (
    FORMAT,
    FORMAT_VERSION,
    ProjectedScaleProbeValidationError,
    require_projected_scale_probes,
    scale_probe_policy,
)
from .resolved_project import canonical_sha256


PROBE_DECIMALS = 9


class ProjectedScaleProbeError(ValueError):
    """Raised when projection evidence cannot form safe scale candidates."""


@dataclass(frozen=True, slots=True)
class ProjectedScaleProbeReport:
    """Frozen candidate-only report with isolated document access."""

    _canonical_json: str

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_json(self) -> str:
        return self._canonical_json

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


def compile_projected_scale_probes(
    projected_bundle: VerifiedProjectedMotionBundle,
    target_profile: Mapping[str, Any],
) -> ProjectedScaleProbeReport:
    """Apply P8 ratios to target setup lengths without emitting animation."""

    try:
        if type(projected_bundle) is not VerifiedProjectedMotionBundle:
            raise ProjectedScaleProbeError(
                "Scale probes require an exact verified P8 bundle"
            )
        _require_verified_bundle(projected_bundle)
        require_motion_target_profile(target_profile)
        projected = projected_bundle.projected_motion
        require_projected_motion_ir(projected)
        document = _document(projected_bundle, projected, target_profile)
        require_projected_scale_probes(
            document,
            projected_bundle=projected_bundle,
            target_profile=target_profile,
        )
        canonical_json = json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        report = ProjectedScaleProbeReport(canonical_json)
        if report.sha256 != canonical_sha256(report.document):
            raise ProjectedScaleProbeError(
                "Projected scale probe identity is inconsistent"
            )
        return report
    except ProjectedScaleProbeError:
        raise
    except (
        MotionTargetValidationError,
        ProjectedMotionBundleContractError,
        ProjectedMotionValidationError,
        ProjectedScaleProbeValidationError,
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
    ) as exc:
        raise ProjectedScaleProbeError(
            f"Projected scale probe compilation failed: {exc}"
        ) from exc


def _require_verified_bundle(bundle: VerifiedProjectedMotionBundle) -> None:
    contract = build_projected_motion_bundle_contract(
        bundle.camera, bundle.projected_motion, bundle.run_manifest
    )
    identities = (
        (contract.clip_id, bundle.clip_id),
        (contract.projected_motion_sha256, bundle.projected_motion_sha256),
        (contract.camera_sha256, bundle.camera_sha256),
        (contract.run_sha256, bundle.run_sha256),
        (contract.legacy_motion_sha256, bundle.legacy_motion_sha256),
        (contract.bundle_sha256, bundle.bundle_sha256),
    )
    raw = bundle.document_bytes
    source = bundle.projected_motion["source"]
    upstream = (
        (source["motion_ir_sha256"], bundle.p7_motion_sha256),
        (source["motion_bundle_sha256"], bundle.p7_bundle_sha256),
        (source["motion_run_sha256"], bundle.p7_run_sha256),
    )
    if bundle.inventory != contract.inventory \
            or raw != contract.document_bytes \
            or any(left != right for left, right in (*identities, *upstream)):
        raise ProjectedScaleProbeError(
            "Verified P8 bundle identities differ from canonical content"
        )


def _document(bundle, projected, target) -> dict[str, Any]:
    target_bones = {bone["role"]: bone for bone in target["bones"]}
    tracks = []
    scales = []
    for projected_track in projected["segment_tracks"]:
        role = projected_track["role"]
        bone = target_bones.get(role)
        if bone is None:
            raise ProjectedScaleProbeError(
                f"Target profile does not bind projected role {role}"
            )
        track, track_scales = _track(projected_track, bone)
        tracks.append(track)
        scales.extend(track_scales)
    if not tracks:
        raise ProjectedScaleProbeError(
            "Projected scale probes require at least one segment track"
        )
    p3 = target["source"]["p3"]
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "project_id": target["project_id"],
        "clip_id": projected["clip_id"],
        "source": {
            "projected_motion_sha256": bundle.projected_motion_sha256,
            "projected_bundle_sha256": bundle.bundle_sha256,
            "camera_sha256": bundle.camera_sha256,
            "p7_motion_sha256": bundle.p7_motion_sha256,
            "target_profile_sha256": canonical_sha256(target),
            "p3_rig_sha256": p3["rig_sha256"],
            "p3_bundle_sha256": p3["bundle_sha256"],
        },
        "policy": scale_probe_policy(),
        "summary": {
            "status": "candidate_only",
            "track_count": len(tracks),
            "sample_count": sum(len(track["samples"]) for track in tracks),
            "collapsed_sample_count": 0,
            "minimum_scale_x_candidate": min(scales),
            "maximum_scale_x_candidate": max(scales),
        },
        "tracks": tracks,
    }


def _track(projected_track, bone):
    samples = projected_track["samples"]
    baseline = float(samples[0]["foreshortening_ratio"])
    if samples[0]["projection_state"] != "observable" or baseline <= 0:
        raise ProjectedScaleProbeError(
            f"Scale probe setup projection is collapsed: {projected_track['role']}"
        )
    setup_length = float(bone["setup_local"]["length_px"])
    output, scales = [], []
    for sample in samples:
        if sample["projection_state"] != "observable":
            raise ProjectedScaleProbeError(
                "Scale probe rejects collapsed projection sample "
                f"{projected_track['role']} frame {sample['source_frame_index']}"
            )
        ratio = float(sample["foreshortening_ratio"])
        scale = _q(ratio / baseline)
        length = _q(setup_length * scale)
        output.append({
            "source_frame_index": sample["source_frame_index"],
            "tick": sample["tick"],
            "foreshortening_ratio": sample["foreshortening_ratio"],
            "scale_x_candidate": scale,
            "candidate_length_px": length,
            "delta_length_px": _q(length - setup_length),
            "projection_state": sample["projection_state"],
        })
        scales.append(scale)
    return {
        "role": projected_track["role"],
        "bone_id": bone["bone_id"],
        "setup_length_px": bone["setup_local"]["length_px"],
        "setup_foreshortening_ratio": samples[0]["foreshortening_ratio"],
        "samples": output,
    }, scales


def _q(value: float) -> float:
    if not math.isfinite(value):
        raise ProjectedScaleProbeError(
            "Projected scale probe produced a non-finite number"
        )
    result = round(float(value), PROBE_DECIMALS)
    return 0.0 if result == 0 else result
