"""Pinned P10.4b1 amplitude-envelope candidate semantics."""

from __future__ import annotations

from fractions import Fraction
import json
from typing import Any

from .body_sway_probe_profile import body_sway_probe_profile
from .body_sway_probe_validation import (
    MAX_DOCUMENT_BYTES as MAX_PROBE_REPORT_BYTES,
    require_body_sway_selection,
)
from .body_sway_review_admission_profile import MAX_ADMISSION_DOCUMENT_BYTES


ANALYZER_ID = "body-sway-amplitude-envelope-analyzer"
ANALYZER_VERSION = "1.0.0"
CANONICALIZATION = "canonical-json-utf8-sort-keys-no-nonfinite"
GAIN_DENOMINATOR = 8
REVIEWED_GAIN_NUMERATOR = 8
MAX_GAIN_NUMERATOR = 8
MAX_ENVELOPE_OWN_BYTES = 2 * 1024 * 1024
MAX_ENVELOPE_DOCUMENT_BYTES = (
    MAX_PROBE_REPORT_BYTES
    + MAX_ADMISSION_DOCUMENT_BYTES
    + MAX_ENVELOPE_OWN_BYTES
)
PROBE_HASH_DOMAIN = "autospine-body-sway-amplitude-envelope-probe/v1"
SCOPE = (
    "sampled_canvas_containment",
    "sampled_fk",
    "sampled_mesh_deformation",
    "shared_index_internal_continuity",
)
EXCLUSIONS = (
    "continuous_time",
    "inter_attachment_seams",
    "raster_visual_quality",
    "runtime_equivalence",
)
RELEASE_BLOCKERS = (
    "continuous_time_safety_unproven",
    "preview_only_timeline",
    "reviewed_seam_anchors_missing",
    "safe_range_unproven",
    "visual_range_unreviewed",
)


def body_sway_amplitude_gain_grid() -> dict[str, int]:
    """Return the sole bounded gain grid as a fresh value."""

    return {
        "minimum_numerator": 0,
        "reviewed_numerator": REVIEWED_GAIN_NUMERATOR,
        "maximum_numerator": MAX_GAIN_NUMERATOR,
        "denominator": GAIN_DENOMINATOR,
    }


def body_sway_amplitude_envelope_parameterization(
    reviewed_selection: Any,
) -> dict[str, Any]:
    """Bind the fixed gain ray to one strictly reviewed selection."""

    require_body_sway_selection(reviewed_selection)
    parameters = reviewed_selection["parameters"]
    return {
        "kind": "uniform_gain_along_reviewed_amplitude_vector",
        "gain_grid": body_sway_amplitude_gain_grid(),
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
        },
        "scope": list(SCOPE),
        "exclusions": list(EXCLUSIONS),
    }


def body_sway_amplitude_envelope_analyzer_profile() -> dict[str, Any]:
    """Return the immutable analyzer identity and sampled-only scope."""

    return {
        "id": ANALYZER_ID,
        "version": ANALYZER_VERSION,
        "canonicalization": CANONICALIZATION,
        "config": {
            "gain_grid": body_sway_amplitude_gain_grid(),
            "time_scope": "sampled-key-states-only",
            "body_sway_probe_profile": body_sway_probe_profile(),
        },
    }


def body_sway_amplitude_envelope_claims() -> dict[str, bool]:
    """Return fixed candidate-only claims without release escalation."""

    return {
        "sampled_visual_approved_at_reviewed_gain": True,
        "sampled_structural_gain_probes": True,
        "safe_range": False,
        "continuous_time": False,
        "visual_range": False,
        "reviewed_seam_anchors": False,
        "motion_instance_v3": False,
        "publishable_timeline": False,
        "release_authority": False,
    }


def body_sway_amplitude_envelope_release_gate() -> dict[str, Any]:
    """Keep every P10.4b1 result explicitly blocked."""

    return {"status": "blocked", "reason_codes": list(RELEASE_BLOCKERS)}


def body_sway_scaled_amplitudes(
    reviewed: list[dict[str, Any]], numerator: int,
) -> list[dict[str, Any]]:
    """Scale the reviewed decimal vector exactly before one float conversion."""

    if type(numerator) is not int \
            or not 0 <= numerator <= MAX_GAIN_NUMERATOR:
        raise ValueError("Body-sway amplitude gain numerator is invalid")
    gain = Fraction(numerator, GAIN_DENOMINATOR)
    return [
        {"bone_id": row["bone_id"], "value": float(
            Fraction(str(row["value"])) * gain)}
        for row in reviewed
    ]


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))
