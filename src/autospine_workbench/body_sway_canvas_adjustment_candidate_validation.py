"""Draft-candidate checks for P10.2 canvas adjustment."""

from __future__ import annotations

from collections.abc import Mapping
import json
import re
from typing import Any

from .body_sway_canvas_adjustment_profile import (
    CANDIDATE_ID_DOMAIN,
    GAIN_DENOMINATOR,
    scaled_body_sway_amplitudes,
)
from .body_sway_canvas_adjustment_probe_validation import require_gain
from .body_sway_probe_validation import require_body_sway_selection
from .idle_behavior_decision_validation_fields import exact_fields, object_value
from .resolved_project import canonical_sha256


_CANDIDATE_ID = re.compile(
    r"^body-sway-canvas-adjustment-[0-9a-f]{64}$"
)
CLAIMS = {
    "sampled_canvas_passed": True,
    "sampled_geometry_passed": True,
    "safe_parameters": False,
    "continuous_time": False,
    "visual_quality": False,
    "release_authority": False,
}


class BodySwayCanvasAdjustmentCandidateFieldError(ValueError):
    """Raised when a draft candidate grants authority or is stale."""


def require_adjustment_candidates(root, source, probes):
    """Require at most one non-zero, sampled-passing, authority-free draft."""

    value = root.get("adjustment_candidates")
    if not isinstance(value, list) or len(value) > 1:
        raise BodySwayCanvasAdjustmentCandidateFieldError(
            "Canvas adjustment candidate inventory is invalid"
        )
    by_gain = {row["gain"]["numerator"]: row for row in probes}
    for row in value:
        exact_fields(object_value(row, "Canvas adjustment candidate"), {
            "candidate_id", "kind", "status", "authority", "gain",
            "parameters", "probe_evidence_sha256",
            "requires_explicit_p10_1_revision", "claims",
        }, "Canvas adjustment candidate")
        numerator = require_gain(row["gain"])
        probe = by_gain.get(numerator)
        if numerator in {0, GAIN_DENOMINATOR} or probe is None \
                or probe["canvas_status"] != "passed" \
                or probe["sampled_geometry_status"] != "passed":
            raise BodySwayCanvasAdjustmentCandidateFieldError(
                "Canvas adjustment candidate lacks passing sampled evidence"
            )
        if row.get("kind") != "uniform_amplitude_gain" \
                or row.get("status") != "unvalidated_draft" \
                or row.get("authority") != "none" \
                or row.get("requires_explicit_p10_1_revision") is not True \
                or row.get("probe_evidence_sha256") != probe["evidence_sha256"] \
                or row.get("claims") != CLAIMS:
            raise BodySwayCanvasAdjustmentCandidateFieldError(
                "Canvas adjustment candidate claims unsupported authority"
            )
        _proposal(
            root["reviewed_selection"], row.get("parameters"), numerator,
        )
        if {item["gain"]["numerator"] for item in probes} \
                != {0, *range(numerator, GAIN_DENOMINATOR + 1)} \
                or any(
                    item["canvas_status"] == "passed"
                    and item["sampled_geometry_status"] == "passed"
                    for item in probes
                    if item["gain"]["numerator"] > numerator
                ):
            raise BodySwayCanvasAdjustmentCandidateFieldError(
                "Canvas adjustment candidate is not the highest passing grid gain"
            )
        expected = body_sway_canvas_adjustment_candidate_id(
            source, root["reviewed_selection"], row,
        )
        if not isinstance(row.get("candidate_id"), str) \
                or not _CANDIDATE_ID.fullmatch(row["candidate_id"]) \
                or row["candidate_id"] != expected:
            raise BodySwayCanvasAdjustmentCandidateFieldError(
                "Canvas adjustment candidate identity is stale"
            )
    return value


def body_sway_canvas_adjustment_candidate_id(
    source: Mapping[str, Any], reviewed_selection: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> str:
    """Bind a draft to the exact P10.1 head, report, gain, and proposal."""

    payload = {
        "domain": CANDIDATE_ID_DOMAIN,
        "source": dict(source),
        "reviewed_selection": dict(reviewed_selection),
        "gain": candidate["gain"],
        "parameters": candidate["parameters"],
        "probe_evidence_sha256": candidate["probe_evidence_sha256"],
    }
    return f"body-sway-canvas-adjustment-{canonical_sha256(payload)}"


def _proposal(reviewed, value, numerator):
    parameters = object_value(value, "Canvas adjustment parameters")
    selection = json.loads(_canonical(reviewed))
    selection["parameters"] = dict(parameters)
    require_body_sway_selection(selection)
    if parameters["cycles"] != reviewed["parameters"]["cycles"] \
            or parameters["per_bone_phase_fraction"] \
            != reviewed["parameters"]["per_bone_phase_fraction"] \
            or parameters["per_bone_amplitude_deg"] \
            != scaled_body_sway_amplitudes(
                reviewed["parameters"]["per_bone_amplitude_deg"], numerator,
            ):
        raise BodySwayCanvasAdjustmentCandidateFieldError(
            "Canvas adjustment may only scale reviewed amplitudes"
        )


def _canonical(value) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
