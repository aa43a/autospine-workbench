"""Compile reviewed heading evidence without producing animation policy."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .heading_evidence_math import (
    HeadingEvidenceMathError,
    heading_frame_math,
    unwrap_yaw_degrees,
)
from .heading_evidence_validation import (
    FORMAT,
    FORMAT_VERSION,
    HeadingEvidenceValidationError,
    heading_policy,
    require_heading_evidence,
)
from .kimodo_npz_reader import decode_kimodo_npz
from .kimodo_policy_evidence import compile_kimodo_policy_evidence
from .kimodo_policy_evidence_validation import require_kimodo_policy_evidence
from .kimodo_policy_map_validation import (
    KimodoPolicyMapError,
    kimodo_policy_map_sha256,
    require_kimodo_policy_map,
)
from .motion_bundle_integrity import VerifiedMotionBundle
from .projected_motion_bundle_integrity import VerifiedProjectedMotionBundle
from .resolved_project import canonical_sha256


class HeadingEvidenceError(ValueError):
    """Raised when reviewed heading semantics cannot bind exact P7/P8 evidence."""


@dataclass(frozen=True, slots=True)
class CompiledHeadingEvidence:
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


def compile_heading_evidence(
    policy_evidence: Mapping[str, Any],
    policy_map: Mapping[str, Any],
    p7_bundle: VerifiedMotionBundle,
    p8_bundle: VerifiedProjectedMotionBundle,
) -> CompiledHeadingEvidence:
    """Map raw heading components and verify them against root-matrix forward."""

    try:
        expected = compile_kimodo_policy_evidence(p7_bundle, p8_bundle)
        require_kimodo_policy_evidence(
            policy_evidence, p7_bundle=p7_bundle, p8_bundle=p8_bundle
        )
        if canonical_sha256(policy_evidence) != expected.sha256:
            raise HeadingEvidenceError(
                "Heading source differs from exact compiled P9.0 evidence"
            )
        mapping, camera = p7_bundle.kimodo_map, p8_bundle.camera
        if mapping is None:
            raise HeadingEvidenceError("Heading source Kimodo map is unavailable")
        require_kimodo_policy_map(
            policy_map, kimodo_map=mapping, camera=camera
        )
        policy = heading_policy(policy_map, camera)
        signal = policy_evidence["signals"]["global_root_heading"]
        frames = [] if signal["status"] == "unavailable" else _frames(
            policy_evidence, policy_map, p7_bundle, camera
        )
        status = "unavailable" if not frames else "available"
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "clip_id": p7_bundle.clip_id,
            "source": _source(policy_evidence, policy_map, p7_bundle, p8_bundle),
            "status": status,
            "policy": policy,
            "frames": frames,
            "summary": _summary(status, frames),
        }
        require_heading_evidence(document)
        canonical = json.dumps(
            document, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        )
        return CompiledHeadingEvidence(canonical)
    except HeadingEvidenceError:
        raise
    except (
        HeadingEvidenceMathError,
        HeadingEvidenceValidationError,
        KimodoPolicyMapError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise HeadingEvidenceError(
            f"Heading evidence compilation failed: {exc}"
        ) from exc


def _frames(evidence, policy_map, p7, camera) -> list[dict[str, Any]]:
    raw_npz, source = p7.raw_npz, p7.kimodo_source
    if raw_npz is None or source is None:
        raise HeadingEvidenceError("Heading exact NPZ source is unavailable")
    snapshot = decode_kimodo_npz(raw_npz, source)
    matrices = snapshot.arrays["global_rot_mats"]
    heading = evidence["signals"]["global_root_heading"]["values"]
    axes = [row["source_axis"] for row in policy_map["heading"]["components"]]
    local_forward = policy_map["heading"]["root_local_forward_axis"]
    rows = []
    for frame, (raw, timing) in enumerate(zip(heading, evidence["timing"]["frames"])):
        matrix = tuple(tuple(matrices.float_at(frame, 0, row, column)
                             for column in range(3)) for row in range(3))
        calculated = heading_frame_math(
            raw, axes, camera["basis"], matrix, local_forward
        )
        rows.append({
            "source_frame_index": timing["source_frame_index"],
            "tick": timing["tick"],
            "raw_components": list(raw),
            **calculated,
            "unwrapped_yaw_deg": 0.0,
        })
    unwrapped = unwrap_yaw_degrees([row["raw_yaw_deg"] for row in rows])
    for row, yaw in zip(rows, unwrapped):
        row["unwrapped_yaw_deg"] = yaw
    maximum = float(
        policy_map["heading"]["crosscheck"]["maximum_angle_error_deg"]
    )
    if any(row["root_forward_angle_error_deg"] > maximum for row in rows):
        raise HeadingEvidenceError(
            "Heading root-forward crosscheck exceeds reviewed tolerance"
        )
    return rows


def _source(evidence, policy_map, p7, p8) -> dict[str, str]:
    upstream = evidence["source"]
    return {
        "policy_evidence_sha256": canonical_sha256(evidence),
        "policy_map_sha256": kimodo_policy_map_sha256(policy_map),
        "p7_motion_ir_sha256": p7.clip_sha256,
        "p7_bundle_sha256": p7.bundle_sha256,
        "p7_run_sha256": p7.run_sha256,
        "raw_npz_sha256": upstream["raw_npz_sha256"],
        "kimodo_map_sha256": upstream["kimodo_map_sha256"],
        "p8_projected_motion_sha256": p8.projected_motion_sha256,
        "p8_bundle_sha256": p8.bundle_sha256,
        "p8_run_sha256": p8.run_sha256,
        "camera_sha256": p8.camera_sha256,
    }


def _summary(status, frames):
    if status == "unavailable":
        return {
            "status": "unavailable",
            "reason_code": "source_heading_unavailable",
            "frame_count": 0,
            "maximum_root_forward_angle_error_deg": None,
        }
    return {
        "status": "available",
        "reason_code": None,
        "frame_count": len(frames),
        "maximum_root_forward_angle_error_deg": max(
            row["root_forward_angle_error_deg"] for row in frames
        ),
    }
