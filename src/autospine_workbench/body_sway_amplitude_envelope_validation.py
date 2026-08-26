"""Strict BodySwayAmplitudeEnvelopeCandidate v1 validation."""
from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from .body_sway_amplitude_envelope_profile import (
    GAIN_DENOMINATOR,
    MAX_ENVELOPE_DOCUMENT_BYTES,
    MAX_GAIN_NUMERATOR,
    PROBE_HASH_DOMAIN,
    REVIEWED_GAIN_NUMERATOR,
    body_sway_amplitude_envelope_analyzer_profile,
    body_sway_amplitude_envelope_claims,
    body_sway_amplitude_envelope_parameterization,
    body_sway_amplitude_envelope_release_gate,
    body_sway_scaled_amplitudes,
)
from .body_sway_probe_evidence_validation import BodySwayProbeEvidenceError, require_checks
from .body_sway_probe_profile import MAX_SAMPLE_COUNT
from .body_sway_probe_validation import (
    BodySwayProbeValidationError,
    body_sway_probe_report_sha256,
    require_body_sway_probe_report,
    require_body_sway_selection,
)
from .body_sway_review_admission_validation import (
    BodySwayReviewAdmissionValidationError,
    body_sway_review_admission_sha256,
    require_body_sway_review_admission,
)
from .idle_behavior_decision_validation_fields import (
    IdleBehaviorDecisionFieldError,
    array_value,
    digest_value,
    exact_fields,
    identifier_value,
    object_value,
    require_timing,
)
from .resolved_project import canonical_sha256
from .body_sway_amplitude_envelope_validation_fields import (
    bounded_integer as _integer,
    canonical_bytes as _canonical,
    contains_forbidden_key as _contains_forbidden_key,
    require_fixed as _fixed,
    require_reviewed_probe as _require_reviewed_probe,
)


FORMAT = "autospine-body-sway-amplitude-envelope-candidate"
FORMAT_VERSION = 1
_TOP = {
    "format", "format_version", "project_id", "clip_id", "source",
    "timing", "reviewed_selection", "parameterization", "probes",
    "analyzer", "claims", "status", "release_gate", "summary",
}
_SOURCE = {
    "review_admission_sha256", "review_admission", "reviewed_probe_report",
}
_PROBE = {
    "gain", "amplitudes", "sample_count", "tick_schedule_sha256",
    "sample_stream_sha256", "checks", "sampled_evidence_sha256", "status",
    "visual_review_status", "preview_relation",
}
_SUMMARY = {
    "gain_probe_count", "sampled_structural_passed_count",
    "sampled_structural_rejected_count", "reviewed_gain_status",
    "sample_evaluation_count",
}
class BodySwayAmplitudeEnvelopeValidationError(ValueError):
    """Raised when an envelope candidate is inconsistent or overclaims."""

def require_body_sway_amplitude_envelope_candidate(
    document: Mapping[str, Any],
) -> None:
    """Validate exact admission binding, gain probes, and blocked semantics."""
    try:
        root = object_value(document, "Body-sway amplitude envelope")
        exact_fields(root, _TOP, "Body-sway amplitude envelope")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root["format_version"] != FORMAT_VERSION:
            raise BodySwayAmplitudeEnvelopeValidationError(
                "Body-sway amplitude envelope format is unsupported"
            )
        project = identifier_value(root.get("project_id"), "project_id")
        clip = identifier_value(root.get("clip_id"), "clip_id")
        admission, report = _source(root.get("source"), project, clip)
        require_timing(root.get("timing"))
        require_body_sway_selection(root.get("reviewed_selection"))
        if _canonical(root["timing"]) != _canonical(admission["timing"]) \
                or _canonical(root["reviewed_selection"]) \
                != _canonical(admission["selection"]):
            raise BodySwayAmplitudeEnvelopeValidationError(
                "Envelope timing or selection differs from its admission"
            )
        expected_parameterization = (
            body_sway_amplitude_envelope_parameterization(
                root["reviewed_selection"]
            )
        )
        _fixed(root.get("parameterization"), expected_parameterization,
               "parameterization")
        probes = _probes(root.get("probes"), root, report)
        _fixed(root.get("analyzer"),
               body_sway_amplitude_envelope_analyzer_profile(), "analyzer")
        _fixed(root.get("claims"),
               body_sway_amplitude_envelope_claims(), "claims")
        if root.get("status") != "candidate_only":
            raise BodySwayAmplitudeEnvelopeValidationError(
                "Amplitude envelope must remain candidate-only"
            )
        _fixed(root.get("release_gate"),
               body_sway_amplitude_envelope_release_gate(), "release gate")
        _summary(root.get("summary"), probes)
        if _contains_forbidden_key(root):
            raise BodySwayAmplitudeEnvelopeValidationError(
                "Amplitude envelope contains a forbidden deployable field"
            )
        if len(_canonical(root)) > MAX_ENVELOPE_DOCUMENT_BYTES:
            raise BodySwayAmplitudeEnvelopeValidationError(
                "Amplitude envelope exceeds its byte limit"
            )
    except BodySwayAmplitudeEnvelopeValidationError:
        raise
    except (
        BodySwayProbeEvidenceError, BodySwayProbeValidationError,
        BodySwayReviewAdmissionValidationError,
        IdleBehaviorDecisionFieldError, KeyError, OverflowError,
        RecursionError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayAmplitudeEnvelopeValidationError(
            f"Body-sway amplitude envelope validation failed: {exc}"
        ) from exc
def body_sway_amplitude_envelope_candidate_sha256(
    document: Mapping[str, Any],
) -> str:
    """Return canonical identity only after strict semantic validation."""
    require_body_sway_amplitude_envelope_candidate(document)
    return canonical_sha256(document)
def body_sway_amplitude_envelope_probe_sha256(
    probe: Mapping[str, Any],
) -> str:
    """Seal every visible probe field except the digest itself."""
    row = object_value(probe, "Amplitude envelope probe")
    if set(row) not in (_PROBE, _PROBE - {"sampled_evidence_sha256"}):
        raise BodySwayAmplitudeEnvelopeValidationError(
            "Amplitude envelope probe fields are unsupported"
        )
    payload = {key: row[key] for key in _PROBE
               if key != "sampled_evidence_sha256"}
    return canonical_sha256({"domain": PROBE_HASH_DOMAIN, "probe": payload})
def _source(value: Any, project: str, clip: str):
    source = object_value(value, "Amplitude envelope source")
    exact_fields(source, _SOURCE, "Amplitude envelope source")
    digest_value(source.get("review_admission_sha256"), "review admission")
    admission = object_value(source.get("review_admission"), "review admission")
    require_body_sway_review_admission(admission)
    report = object_value(source.get("reviewed_probe_report"), "probe report")
    require_body_sway_probe_report(report)
    report_sha = body_sway_probe_report_sha256(report)
    expected_chain = {"body_sway_probe_report_sha256": report_sha,
                      **report["source"]}
    if body_sway_review_admission_sha256(admission) \
            != source["review_admission_sha256"] \
            or admission["project_id"] != project \
            or admission["clip_id"] != clip \
            or report["project_id"] != project \
            or report["clip_id"] != clip \
            or report["status"] != "manual_visual_required" \
            or report["timing"] != admission["timing"] \
            or report["selection"] != admission["selection"] \
            or admission["source"]["p10_chain"] != expected_chain:
        raise BodySwayAmplitudeEnvelopeValidationError(
            "Envelope source differs from its exact review admission"
        )
    return admission, report
def _probes(value: Any, root: Mapping[str, Any], report) -> list[Mapping[str, Any]]:
    probes = array_value(value, "Amplitude envelope probes", minimum=9,
                         maximum=9)
    parameterization = root["parameterization"]
    reviewed = parameterization["reviewed_amplitudes"]
    expected_schedule = None
    for numerator, raw in enumerate(probes):
        row = object_value(raw, "Amplitude envelope probe")
        exact_fields(row, _PROBE, "Amplitude envelope probe")
        _gain(row.get("gain"), numerator)
        _amplitudes(row.get("amplitudes"), reviewed, numerator)
        count = _integer(row.get("sample_count"), 2, MAX_SAMPLE_COUNT,
                         "sample count")
        digest_value(row.get("tick_schedule_sha256"), "tick schedule")
        digest_value(row.get("sample_stream_sha256"), "sample stream")
        schedule = (count, row["tick_schedule_sha256"])
        if expected_schedule is None:
            expected_schedule = schedule
        elif schedule != expected_schedule:
            raise BodySwayAmplitudeEnvelopeValidationError(
                "Gain probes must share one exact sample schedule"
            )
        evidence = _checks(row.get("checks"), root["timing"], count)
        expected_status = "sampled_structural_rejected" \
            if evidence["structural_rejected"] \
            else "sampled_structural_passed"
        if row.get("status") != expected_status:
            raise BodySwayAmplitudeEnvelopeValidationError(
                "Gain probe status differs from structural checks"
            )
        reviewed_gain = numerator == REVIEWED_GAIN_NUMERATOR
        expected_visual = "approved" if reviewed_gain else "not_reviewed"
        expected_relation = "exact-reviewed-probe-replay" if reviewed_gain \
            else "hypothetical-scaled-key-states"
        if row.get("visual_review_status") != expected_visual \
                or row.get("preview_relation") != expected_relation:
            raise BodySwayAmplitudeEnvelopeValidationError(
                "Gain probe visual-review relation is invalid"
            )
        digest_value(row.get("sampled_evidence_sha256"), "sampled evidence")
        if row["sampled_evidence_sha256"] \
                != body_sway_amplitude_envelope_probe_sha256(row):
            raise BodySwayAmplitudeEnvelopeValidationError(
                "Gain probe evidence digest differs from its visible row"
            )
        if reviewed_gain:
            _require_reviewed_probe(row, report)
    return probes
def _gain(value: Any, numerator: int) -> None:
    row = object_value(value, "Amplitude envelope gain")
    exact_fields(row, {"numerator", "denominator"}, "Amplitude envelope gain")
    if type(row.get("numerator")) is not int \
            or row["numerator"] != numerator \
            or type(row.get("denominator")) is not int \
            or row["denominator"] != GAIN_DENOMINATOR \
            or not 0 <= numerator <= MAX_GAIN_NUMERATOR:
        raise BodySwayAmplitudeEnvelopeValidationError(
            "Amplitude envelope gain is outside the pinned grid"
        )
def _amplitudes(value: Any, reviewed: list[Any], numerator: int) -> None:
    rows = array_value(value, "Scaled amplitudes", minimum=len(reviewed),
                       maximum=len(reviewed))
    expected = body_sway_scaled_amplitudes(reviewed, numerator)
    if _canonical(rows) != _canonical(expected):
        raise BodySwayAmplitudeEnvelopeValidationError(
            "Scaled amplitudes differ from reviewed amplitudes times gain"
        )
def _checks(value: Any, timing: Mapping[str, Any], count: int):
    rows = array_value(value, "Amplitude envelope checks", minimum=7, maximum=7)
    indexed = {row.get("check_id"): row for row in rows
               if isinstance(row, Mapping)}
    required = {
        "loop_closure", "fk_finite", "sampled_mesh_deformation",
        "sampled_canvas_containment", "shared_index_internal_continuity",
    }
    if not required <= set(indexed):
        raise BodySwayAmplitudeEnvelopeValidationError(
            "Amplitude envelope structural checks are incomplete"
        )
    loop_closed = bool(
        timing["loop"] and indexed["loop_closure"].get("status") == "passed"
    )
    return require_checks(
        rows, loop=timing["loop"], schedule_count=count,
        rig_bone_count=indexed["fk_finite"].get("subject_count"),
        attachment_count=indexed["sampled_canvas_containment"].get(
            "subject_count"
        ),
        mesh_attachment_count=indexed["sampled_mesh_deformation"].get(
            "subject_count"
        ),
        loop_pose_closed=loop_closed,
    )
def _summary(value: Any, probes: list[Mapping[str, Any]]) -> None:
    row = object_value(value, "Amplitude envelope summary")
    exact_fields(row, _SUMMARY, "Amplitude envelope summary")
    passed = sum(item["status"] == "sampled_structural_passed"
                 for item in probes)
    expected = {
        "gain_probe_count": len(probes),
        "sampled_structural_passed_count": passed,
        "sampled_structural_rejected_count": len(probes) - passed,
        "reviewed_gain_status": probes[REVIEWED_GAIN_NUMERATOR]["status"],
        "sample_evaluation_count": sum(item["sample_count"] for item in probes),
    }
    if row != expected or any(
        type(row[field]) is not int for field in _SUMMARY
        if field != "reviewed_gain_status"
    ):
        raise BodySwayAmplitudeEnvelopeValidationError(
            "Amplitude envelope summary differs from its probes"
        )
