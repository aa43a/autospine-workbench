"""Compile exact reviewed evidence into version-neutral motion policy v1."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .ik_target_geometry import SOURCE_IDENTITY_FIELDS
from .mesh_bundle_admission import (
    MeshBundleAdmissionError,
    require_exact_mesh_bundle,
)
from .mesh_bundle_integrity import VerifiedMeshBundle
from .motion_policy_decision_validation import (
    MotionPolicyDecisionValidationError,
    motion_policy_decision_sha256,
    require_motion_policy_decision,
)
from .reviewed_draw_order import (
    ReviewedDrawOrderError,
    compile_reviewed_slot_order,
)
from .reviewed_motion_policy_validation import (
    FORMAT,
    FORMAT_VERSION,
    SEMANTICS,
    ReviewedMotionPolicyValidationError,
    require_reviewed_motion_policy,
    reviewed_motion_policy_sha256,
)
from .reviewed_root_correction import (
    ReviewedRootCorrectionError,
    compile_reviewed_root_correction,
)


class ReviewedMotionPolicyError(ValueError):
    """Raised when exact reviewed inputs cannot form a runtime-neutral policy."""


@dataclass(frozen=True, slots=True)
class ReviewedMotionPolicy:
    """Frozen canonical policy with isolated document access."""

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


def compile_reviewed_motion_policy(
    decision: Mapping[str, Any],
    foot_candidates: Mapping[str, Any],
    depth_candidates: Mapping[str, Any],
    mesh_bundle: VerifiedMeshBundle,
) -> ReviewedMotionPolicy:
    """Compile one approved decision without mutating P5 or emitting Spine."""

    try:
        require_motion_policy_decision(
            decision,
            foot_candidates=foot_candidates,
            depth_candidates=depth_candidates,
        )
        rig = require_exact_mesh_bundle(mesh_bundle)
        _require_mesh_source(decision, mesh_bundle)
        setup_slots = [
            row["id"] for row in sorted(
                rig["slots"],
                key=lambda row: (row["setup_draw_order"], row["id"]),
            )
        ]
        root_keys = compile_reviewed_root_correction(
            decision, foot_candidates, depth_candidates
        )
        timing = dict(depth_candidates["timing"])
        if len(root_keys) != timing["frame_count"]:
            raise ReviewedMotionPolicyError(
                "Root correction does not cover the complete frame schedule"
            )
        slot_order = compile_reviewed_slot_order(
            decision, foot_candidates, depth_candidates, setup_slots
        )
        source = _copy(decision["source"])
        source["motion_policy_decision_sha256"] = (
            motion_policy_decision_sha256(
                decision,
                foot_candidates=foot_candidates,
                depth_candidates=depth_candidates,
            )
        )
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "project_id": decision["project_id"],
            "clip_id": decision["clip_id"],
            "source": source,
            "timing": timing,
            "semantics": dict(SEMANTICS),
            "root_correction_keys": root_keys,
            "slot_order": slot_order,
        }
        require_reviewed_motion_policy(document)
        value = ReviewedMotionPolicy(_canonical(document))
        if value.sha256 != reviewed_motion_policy_sha256(value.document):
            raise ReviewedMotionPolicyError(
                "Reviewed motion-policy identity is inconsistent"
            )
        return value
    except ReviewedMotionPolicyError:
        raise
    except (
        KeyError,
        MeshBundleAdmissionError,
        MotionPolicyDecisionValidationError,
        ReviewedDrawOrderError,
        ReviewedMotionPolicyValidationError,
        ReviewedRootCorrectionError,
        TypeError,
        ValueError,
    ) as exc:
        raise ReviewedMotionPolicyError(
            f"Reviewed motion-policy compilation failed: {exc}"
        ) from exc


def _require_mesh_source(decision, bundle: VerifiedMeshBundle) -> None:
    expected = {
        field: getattr(bundle, field) for field in SOURCE_IDENTITY_FIELDS
    }
    if decision["project_id"] != bundle.project_id \
            or decision["source"]["p3"] != expected:
        raise ReviewedMotionPolicyError(
            "Reviewed motion policy and exact P3 bundle differ"
        )


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
