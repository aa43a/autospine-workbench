"""Pinned semantics for P10.2 sampled canvas-adjustment candidates."""

from __future__ import annotations

from fractions import Fraction
import json
from typing import Any


FORMAT = "autospine-body-sway-canvas-adjustment-candidates"
FORMAT_VERSION = 1
ANALYZER_ID = "body-sway-canvas-adjustment-analyzer"
ANALYZER_VERSION = "1.0.0"
GAIN_DENOMINATOR = 8
REVIEWED_GAIN_NUMERATOR = GAIN_DENOMINATOR
GAIN_NUMERATORS = tuple(range(GAIN_DENOMINATOR + 1))
EVIDENCE_HASH_DOMAIN = "autospine-body-sway-canvas-gain-evidence/v1"
CANDIDATE_ID_DOMAIN = "autospine-body-sway-canvas-adjustment-candidate/v1"

SEMANTICS = {
    "scope": "sampled-canvas-adjustment-candidate-only",
    "authority": "none",
    "human_decision_emitted": False,
    "review_revision_written": False,
    "temporary_preview_emitted": False,
    "sampled_canvas_observation_claimed": True,
    "discrete_gain_samples_are_safe_interval": False,
    "safe_parameters_claimed": False,
    "continuous_time_safety_claimed": False,
    "visual_quality_claimed": False,
    "runtime_equivalence_claimed": False,
    "inter_attachment_seam_safety_claimed": False,
}

RELEASE_BLOCKERS = (
    "candidate_requires_explicit_p10_1_review",
    "continuous_time_safety_unproven",
    "manual_runtime_preview_required",
    "reviewed_seam_anchors_missing",
    "safe_parameters_unproven",
)


def body_sway_canvas_adjustment_analyzer_profile() -> dict[str, Any]:
    """Return the immutable, finite diagnostic search profile."""

    return {
        "id": ANALYZER_ID,
        "version": ANALYZER_VERSION,
        "config": {
            "parameterization": "uniform-amplitude-gain",
            "gain_denominator": GAIN_DENOMINATOR,
            "reviewed_gain_numerator": REVIEWED_GAIN_NUMERATOR,
            "search_order": list(range(GAIN_DENOMINATOR - 1, 0, -1)),
            "search_stop": "first-sampled-structural-pass",
            "zero_gain_probe_required_after_reviewed_failure": True,
            "sample_schedule": "exact-p10.2-probe-schedule",
        },
    }


def body_sway_canvas_adjustment_release_gate() -> dict[str, Any]:
    """Keep every automatic result outside human and release authority."""

    return {"status": "blocked", "reason_codes": list(RELEASE_BLOCKERS)}


def scaled_body_sway_amplitudes(
    rows: list[dict[str, Any]], numerator: int,
) -> list[dict[str, Any]]:
    """Scale reviewed amplitudes exactly along the pinned finite gain ray."""

    if type(numerator) is not int or numerator not in GAIN_NUMERATORS:
        raise ValueError("Body-sway canvas adjustment gain is invalid")
    gain = Fraction(numerator, GAIN_DENOMINATOR)
    return [
        {
            "bone_id": row["bone_id"],
            "value": float(Fraction(str(row["value"])) * gain),
        }
        for row in rows
    ]


def copy_json(value: Any) -> Any:
    """Return one canonical JSON-detached value."""

    return json.loads(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))
