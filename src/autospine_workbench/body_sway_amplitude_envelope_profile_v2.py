"""Pinned P10.4b1 v2 amplitude-envelope semantics."""

from __future__ import annotations

from fractions import Fraction
import json
from typing import Any

from .body_sway_probe_profile import body_sway_probe_profile


ANALYZER_ID = "body-sway-amplitude-envelope-analyzer-v2"
ANALYZER_VERSION = "2.0.0"
CANONICALIZATION = "canonical-json-utf8-sort-keys-no-nonfinite"
GAIN_DENOMINATOR = 8
REVIEWED_GAIN_NUMERATOR = 8
PROBE_HASH_DOMAIN = "autospine-body-sway-amplitude-envelope-probe/v2"
MAX_DOCUMENT_BYTES = 6 * 1024 * 1024
SCOPE = (
    "reviewed_world_viewport_sampled_canvas_containment",
    "sampled_fk",
    "sampled_mesh_deformation",
    "shared_index_internal_continuity",
)
EXCLUSIONS = (
    "continuous_time",
    "inter_attachment_seams",
    "visual_gain_range",
    "official_runtime_continuous_equivalence",
)
RELEASE_BLOCKERS = (
    "continuous_preview_model_safety_unproven",
    "motion_instance_v3_not_emitted",
    "publishable_timeline_not_emitted",
    "reviewed_seam_anchors_missing",
    "runtime_continuous_equivalence_unproven",
    "visual_gain_range_unreviewed",
)


def amplitude_gain_grid_v2() -> dict[str, int]:
    return {
        "minimum_numerator": 0,
        "reviewed_numerator": REVIEWED_GAIN_NUMERATOR,
        "maximum_numerator": REVIEWED_GAIN_NUMERATOR,
        "denominator": GAIN_DENOMINATOR,
    }


def amplitude_parameterization_v2(selection: dict[str, Any]) \
        -> dict[str, Any]:
    parameters = selection["parameters"]
    return {
        "kind": "uniform_gain_along_reviewed_amplitude_vector",
        "gain_grid": amplitude_gain_grid_v2(),
        "cycles": parameters["cycles"],
        "reviewed_amplitudes": _copy(
            parameters["per_bone_amplitude_deg"]
        ),
        "phase_fractions": _copy(
            parameters["per_bone_phase_fraction"]
        ),
        "preview_time_model": {
            "rotation_interpolation": "sampled-linear",
            "root_translation": "exact-motion-instance-v2",
            "sampling": "p10-probe-schedule",
            "canvas": "capture-framing-world-viewport-v2",
        },
        "scope": list(SCOPE),
        "exclusions": list(EXCLUSIONS),
    }


def amplitude_analyzer_profile_v2() -> dict[str, Any]:
    return {
        "id": ANALYZER_ID,
        "version": ANALYZER_VERSION,
        "canonicalization": CANONICALIZATION,
        "config": {
            "gain_grid": amplitude_gain_grid_v2(),
            "time_scope": "sampled-key-states-only",
            "body_sway_probe_profile": body_sway_probe_profile(),
            "viewport_semantics": "reviewed-world-viewport-v2",
        },
    }


def amplitude_claims_v2() -> dict[str, bool]:
    return {
        "official_runtime_sampled_cases_approved_at_reviewed_gain": True,
        "sampled_structural_gain_probes": True,
        "continuous_preview_model_structural_safety": False,
        "safe_range": False,
        "visual_gain_range": False,
        "reviewed_seam_anchors": False,
        "official_runtime_continuous_equivalence": False,
        "motion_instance_v3": False,
        "publishable_timeline": False,
        "release_authority": False,
    }


def amplitude_release_gate_v2() -> dict[str, Any]:
    return {"status": "blocked", "reason_codes": list(RELEASE_BLOCKERS)}


def scaled_amplitudes_v2(rows, numerator: int):
    if type(numerator) is not int \
            or not 0 <= numerator <= REVIEWED_GAIN_NUMERATOR:
        raise ValueError("Body-sway v2 amplitude gain is invalid")
    gain = Fraction(numerator, GAIN_DENOMINATOR)
    return [{
        "bone_id": row["bone_id"],
        "value": float(Fraction(str(row["value"])) * gain),
    } for row in rows]


def _copy(value):
    return json.loads(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))


__all__ = [
    "GAIN_DENOMINATOR", "MAX_DOCUMENT_BYTES", "PROBE_HASH_DOMAIN",
    "REVIEWED_GAIN_NUMERATOR", "amplitude_analyzer_profile_v2",
    "amplitude_claims_v2", "amplitude_gain_grid_v2",
    "amplitude_parameterization_v2", "amplitude_release_gate_v2",
    "scaled_amplitudes_v2",
]
