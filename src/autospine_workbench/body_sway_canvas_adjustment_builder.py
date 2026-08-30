"""Small deterministic builders for P10.2 canvas-adjustment results."""

from __future__ import annotations

from .body_sway_canvas_adjustment_candidate_validation import CLAIMS
from .body_sway_canvas_adjustment_probe import probe_body_sway_canvas_gain
from .body_sway_canvas_adjustment_profile import (
    GAIN_DENOMINATOR,
    copy_json,
    scaled_body_sway_amplitudes,
)


def search_body_sway_canvas_adjustment(reviewed_selection, prepared, probes):
    """Search descending fixed gains and stop at the first sampled pass."""

    for numerator in range(GAIN_DENOMINATOR - 1, 0, -1):
        probe = probe_body_sway_canvas_gain(prepared, numerator)
        probes.append(probe)
        if probe["canvas_status"] == "passed" \
                and probe["sampled_geometry_status"] == "passed":
            parameters = reviewed_selection["parameters"]
            return {
                "kind": "uniform_amplitude_gain",
                "status": "unvalidated_draft",
                "authority": "none",
                "gain": copy_json(probe["gain"]),
                "parameters": {
                    "cycles": parameters["cycles"],
                    "per_bone_amplitude_deg": scaled_body_sway_amplitudes(
                        parameters["per_bone_amplitude_deg"], numerator,
                    ),
                    "per_bone_phase_fraction": copy_json(
                        parameters["per_bone_phase_fraction"]
                    ),
                },
                "probe_evidence_sha256": probe["evidence_sha256"],
                "requires_explicit_p10_1_revision": True,
                "claims": copy_json(CLAIMS),
            }
    return None


def body_sway_canvas_adjustment_source(inputs, head, report):
    """Bind the candidate to the current decision and every probe input."""

    return {
        "probe_inputs": inputs.source,
        "current_p10_1_head": {
            "candidate_sha256": inputs.source[
                "idle_behavior_candidates_sha256"
            ],
            "decision_sha256": head.decision_sha256,
            "revision": head.current_revision,
        },
        "body_sway_probe_report_sha256": report.sha256,
    }


def canvas_check_from_report(report):
    """Project the exact authoritative P10.2 canvas check."""

    row = next(check for check in report["checks"]
               if check["check_id"] == "sampled_canvas_containment")
    return {field: row[field] for field in (
        "status", "sample_count", "failure_count", "evidence_sha256",
    )}


def require_reviewed_canvas_probe(check, probe):
    """Require the rich reviewed-gain aggregation to match exact P10.2."""

    if check["status"] != probe["canvas_status"] \
            or check["sample_count"] != probe["sample_count"] \
            or check["failure_count"] != probe["canvas_failure_tick_count"]:
        raise ValueError(
            "Canvas adjustment reviewed gain differs from exact P10.2"
        )
