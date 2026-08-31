"""Deterministic, authority-free region-to-bone rebind candidates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .body_sway_probe_math import BodySwayPoseSample
from .region_rebind_geometry import (
    candidate_rank,
    evaluate_region_rebind_candidate,
    prepare_region_rebind_geometry,
    quantize,
)
from .region_rebind_inputs import (
    RegionRebindInputError,
    admit_region_rebind_inputs,
    require_digest,
    safe_identifier,
)
from .region_rebind_profile import (
    FORMAT,
    FORMAT_VERSION,
    MIN_RELATIVE_MOTION_IMPROVEMENT,
    RANK_TIE_RELATIVE_TOLERANCE,
    region_rebind_analyzer_profile,
    region_rebind_analyzer_profile_sha256,
    region_rebind_semantics,
)
from .resolved_project import canonical_sha256


class RegionRebindCandidateError(ValueError):
    """Raised when exact inputs cannot produce bounded rebind evidence."""


@dataclass(frozen=True, slots=True)
class RegionRebindCandidateArtifact:
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


def compile_region_rebind_candidates(
    rig: Mapping[str, Any],
    motion_samples: Sequence[BodySwayPoseSample],
    *,
    project_id: str,
    motion_sha256: str,
    attachment_id: str,
    candidate_bone_ids: Sequence[str] | None = None,
) -> RegionRebindCandidateArtifact:
    """Compare one region across current/adjacent bones without changing state."""

    try:
        project_id = safe_identifier(project_id, "project_id")
        attachment_id = safe_identifier(attachment_id, "attachment_id")
        motion_sha256 = require_digest(motion_sha256, "motion_sha256")
        admitted = admit_region_rebind_inputs(
            rig, motion_samples, attachment_id, candidate_bone_ids,
        )
        source = _source(
            rig, admitted, attachment_id, motion_sha256,
        )
        prepared = prepare_region_rebind_geometry(admitted)
        rows = tuple(
            evaluate_region_rebind_candidate(prepared, source, bone_id)
            for bone_id in admitted.candidate_bone_ids
        )
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "project_id": project_id,
            "source": source,
            "analyzer": region_rebind_analyzer_profile(),
            "semantics": region_rebind_semantics(),
            "candidates": list(rows),
            "recommendation": _recommend(admitted.current_bone_id, rows),
            "status": "candidate_only",
        }
        from .region_rebind_validation import require_region_rebind_candidates
        require_region_rebind_candidates(document)
        return RegionRebindCandidateArtifact(_canonical(document).decode("utf-8"))
    except RegionRebindCandidateError:
        raise
    except (
        KeyError, OverflowError, RegionRebindInputError, TypeError, ValueError,
    ) as exc:
        raise RegionRebindCandidateError(
            f"Region rebind candidate compilation failed: {exc}"
        ) from exc


def _source(rig, admitted, attachment_id, motion_sha256):
    return {
        "rig_sha256": canonical_sha256(rig),
        "motion_sha256": motion_sha256,
        "motion_samples_sha256": canonical_sha256({
            "samples": [row[0].to_dict() for row in admitted.samples]
        }),
        "motion_sample_count": len(admitted.samples),
        "attachment_id": attachment_id,
        "slot_id": admitted.slot_id,
        "current_bone_id": admitted.current_bone_id,
        "candidate_bone_ids_sha256": canonical_sha256({
            "bone_ids": list(admitted.candidate_bone_ids)
        }),
        "analyzer_profile_sha256": region_rebind_analyzer_profile_sha256(),
    }


def _recommend(current, rows):
    ordered = sorted(rows, key=candidate_rank)
    best = ordered[0]
    current_row = next(row for row in rows if row["bone_id"] == current)
    current_value = current_row["metrics"]["normalized_centroid_motion_rms"]
    best_value = best["metrics"]["normalized_centroid_motion_rms"]
    coverage_gain = (
        best["metrics"]["setup_subtree_segment_coverage_count"]
        - current_row["metrics"]["setup_subtree_segment_coverage_count"]
    )
    improvement = 0.0 if current_value <= 1e-12 else (
        current_value - best_value
    ) / current_value
    tied = len(ordered) > 1 and _relative_gap(
        best_value,
        ordered[1]["metrics"]["normalized_centroid_motion_rms"],
    ) <= RANK_TIE_RELATIVE_TOLERANCE
    if best["bone_id"] == current:
        status = "keep_current"
        reasons = ["current_binding_has_lowest_motion_extent"]
    elif coverage_gain <= 0 or tied \
            or improvement < MIN_RELATIVE_MOTION_IMPROVEMENT:
        status = "ambiguous"
        reasons = [
            "insufficient_combined_spatial_and_motion_evidence"
        ]
    else:
        status = "recommended"
        reasons = [
            "region_envelope_spans_parent_and_child_segments",
            "lower_root_compensated_motion_extent",
            "one_hop_same_chain",
        ]
        if best["metrics"]["viewport_overflow_sample_count"] \
                < current_row["metrics"]["viewport_overflow_sample_count"]:
            reasons.append("reduced_viewport_overflow_diagnostic")
    return {
        "status": status,
        "candidate_id": best["candidate_id"],
        "from_bone_id": current,
        "to_bone_id": best["bone_id"],
        "relative_motion_improvement": quantize(max(0.0, improvement)),
        "reason_codes": reasons,
        "authority": "none",
        "requires_explicit_review": True,
    }


def _relative_gap(left, right):
    return abs(right - left) / max(abs(left), abs(right), 1e-12)


def _canonical(value):
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
