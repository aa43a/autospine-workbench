"""Strict semantic validation for P10.4b1 amplitude candidate v2."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .body_sway_amplitude_envelope_profile_v2 import (
    GAIN_DENOMINATOR, MAX_DOCUMENT_BYTES, PROBE_HASH_DOMAIN,
    REVIEWED_GAIN_NUMERATOR, amplitude_analyzer_profile_v2,
    amplitude_claims_v2, amplitude_parameterization_v2,
    amplitude_release_gate_v2,
)
from .body_sway_amplitude_envelope_validation import (
    _amplitudes, _checks, _gain, _summary,
)
from .body_sway_amplitude_envelope_validation_fields import (
    bounded_integer as _integer,
    canonical_bytes as _canonical,
    contains_forbidden_key as _contains_forbidden_key,
    require_fixed as _fixed,
)
from .body_sway_probe_profile import MAX_SAMPLE_COUNT
from .body_sway_probe_validation import (
    body_sway_probe_report_sha256, require_body_sway_probe_report,
    require_body_sway_selection,
)
from .body_sway_review_admission_validation_v2 import (
    body_sway_review_admission_sha256_v2,
    require_body_sway_review_admission_v2,
)
from .idle_behavior_decision_validation_fields import (
    array_value, digest_value, exact_fields, identifier_value,
    object_value, require_timing,
)
from .resolved_project import canonical_sha256


FORMAT = "autospine-body-sway-amplitude-envelope-candidate"
FORMAT_VERSION = 2
_TOP = {
    "format", "format_version", "project_id", "clip_id", "source",
    "timing", "reviewed_selection", "parameterization", "probes",
    "analyzer", "claims", "status", "release_gate", "summary",
}
_SOURCE = {
    "review_admission_v2_sha256", "review_admission_v2",
    "temporary_preview_v2_sha256", "preview_projection_v2_sha256",
    "reviewed_world_viewport", "reviewed_probe_report",
}
_PROBE = {
    "gain", "amplitudes", "sample_count", "tick_schedule_sha256",
    "sample_stream_sha256", "checks", "sampled_evidence_sha256",
    "status", "visual_review_status", "preview_relation",
}


class BodySwayAmplitudeEnvelopeValidationV2Error(ValueError):
    """Raised when a v2 candidate is detached, malformed, or overclaims."""


def require_body_sway_amplitude_envelope_candidate_v2(
    document: Mapping[str, Any],
) -> None:
    try:
        root = object_value(document, "Amplitude envelope v2")
        exact_fields(root, _TOP, "Amplitude envelope v2")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root["format_version"] != FORMAT_VERSION:
            raise BodySwayAmplitudeEnvelopeValidationV2Error(
                "Amplitude envelope v2 format is unsupported"
            )
        project = identifier_value(root.get("project_id"), "project_id")
        clip = identifier_value(root.get("clip_id"), "clip_id")
        admission, report = _source(root.get("source"), project, clip)
        require_timing(root.get("timing"))
        require_body_sway_selection(root.get("reviewed_selection"))
        if root["timing"] != admission["timing"] \
                or root["reviewed_selection"] != admission["selection"]:
            raise BodySwayAmplitudeEnvelopeValidationV2Error(
                "Amplitude v2 timing or selection differs from admission"
            )
        _fixed(
            root.get("parameterization"),
            amplitude_parameterization_v2(root["reviewed_selection"]),
            "parameterization v2",
        )
        probes = _probes(root.get("probes"), root, report)
        _fixed(root.get("analyzer"), amplitude_analyzer_profile_v2(),
               "analyzer v2")
        _fixed(root.get("claims"), amplitude_claims_v2(), "claims v2")
        if root.get("status") != "candidate_only":
            raise BodySwayAmplitudeEnvelopeValidationV2Error(
                "Amplitude envelope v2 must remain candidate-only"
            )
        _fixed(root.get("release_gate"), amplitude_release_gate_v2(),
               "release gate v2")
        _summary(root.get("summary"), probes)
        if _contains_forbidden_key(root):
            raise BodySwayAmplitudeEnvelopeValidationV2Error(
                "Amplitude envelope v2 contains a deployable field"
            )
        if len(_canonical(root)) > MAX_DOCUMENT_BYTES:
            raise BodySwayAmplitudeEnvelopeValidationV2Error(
                "Amplitude envelope v2 exceeds its byte limit"
            )
    except BodySwayAmplitudeEnvelopeValidationV2Error:
        raise
    except Exception as exc:
        raise BodySwayAmplitudeEnvelopeValidationV2Error(
            f"Amplitude envelope v2 validation failed: {exc}"
        ) from exc


def body_sway_amplitude_envelope_candidate_sha256_v2(document) -> str:
    require_body_sway_amplitude_envelope_candidate_v2(document)
    return canonical_sha256(document)


def body_sway_amplitude_envelope_probe_sha256_v2(probe) -> str:
    row = object_value(probe, "Amplitude envelope v2 probe")
    if set(row) not in (_PROBE, _PROBE - {"sampled_evidence_sha256"}):
        raise BodySwayAmplitudeEnvelopeValidationV2Error(
            "Amplitude envelope v2 probe fields are unsupported"
        )
    payload = {
        key: row[key] for key in _PROBE
        if key != "sampled_evidence_sha256"
    }
    return canonical_sha256({"domain": PROBE_HASH_DOMAIN, "probe": payload})


def _source(value, project, clip):
    source = object_value(value, "Amplitude envelope v2 source")
    exact_fields(source, _SOURCE, "Amplitude envelope v2 source")
    for field in (
        "review_admission_v2_sha256", "temporary_preview_v2_sha256",
        "preview_projection_v2_sha256",
    ):
        digest_value(source.get(field), field)
    admission = object_value(
        source.get("review_admission_v2"), "review admission v2"
    )
    require_body_sway_review_admission_v2(admission)
    report = object_value(
        source.get("reviewed_probe_report"), "reviewed probe report"
    )
    require_body_sway_probe_report(report)
    evidence = admission["source"]["evidence"]
    preview_source = admission["source"]["preview_source"]
    if body_sway_review_admission_sha256_v2(admission) \
            != source["review_admission_v2_sha256"] \
            or admission["project_id"] != project \
            or admission["clip_id"] != clip \
            or report["project_id"] != project \
            or report["clip_id"] != clip \
            or report["timing"] != admission["timing"] \
            or report["selection"] != admission["selection"] \
            or body_sway_probe_report_sha256(report) \
                != preview_source["body_sway_probe_report_sha256"] \
            or source["temporary_preview_v2_sha256"] \
                != admission["source"]["execution"][
                    "temporary_preview_v2_sha256"
                ] \
            or source["reviewed_world_viewport"] \
                != evidence["world_viewport"]:
        raise BodySwayAmplitudeEnvelopeValidationV2Error(
            "Amplitude envelope v2 source is cross-wired"
        )
    return admission, report


def _probes(value, root, report):
    probes = array_value(
        value, "Amplitude envelope v2 probes", minimum=9, maximum=9,
    )
    schedule = None
    reviewed = root["parameterization"]["reviewed_amplitudes"]
    for numerator, raw in enumerate(probes):
        row = object_value(raw, "Amplitude envelope v2 probe")
        exact_fields(row, _PROBE, "Amplitude envelope v2 probe")
        _gain(row.get("gain"), numerator)
        _amplitudes(row.get("amplitudes"), reviewed, numerator)
        count = _integer(
            row.get("sample_count"), 2, MAX_SAMPLE_COUNT, "sample count",
        )
        digest_value(row.get("tick_schedule_sha256"), "tick schedule")
        digest_value(row.get("sample_stream_sha256"), "sample stream")
        evidence = _checks(row.get("checks"), root["timing"], count)
        expected = "sampled_structural_rejected" \
            if evidence["structural_rejected"] \
            else "sampled_structural_passed"
        current_schedule = (
            count, row["tick_schedule_sha256"]
        )
        if row.get("status") != expected \
                or schedule is not None and schedule != current_schedule:
            raise BodySwayAmplitudeEnvelopeValidationV2Error(
                "Amplitude envelope v2 probe status or schedule differs"
            )
        schedule = current_schedule
        _probe_relation(row, numerator, report)
        if numerator == REVIEWED_GAIN_NUMERATOR:
            _require_reviewed_probe_v2(row, report)
        digest_value(row.get("sampled_evidence_sha256"), "probe v2")
        if row["sampled_evidence_sha256"] \
                != body_sway_amplitude_envelope_probe_sha256_v2(row):
            raise BodySwayAmplitudeEnvelopeValidationV2Error(
                "Amplitude envelope v2 probe digest differs"
            )
    return probes


def _probe_relation(row, numerator, report):
    reviewed = numerator == REVIEWED_GAIN_NUMERATOR
    visual = "official_runtime_sampled_cases_approved" \
        if reviewed else "not_reviewed"
    relation = "exact-preview-v2-structural-replay-reviewed-world-viewport" \
        if reviewed else "hypothetical-scaled-key-states"
    if row.get("visual_review_status") != visual \
            or row.get("preview_relation") != relation:
        raise BodySwayAmplitudeEnvelopeValidationV2Error(
            "Amplitude envelope v2 visual relation is invalid"
        )
    if reviewed and (
        row["sample_stream_sha256"]
        != report["sample_stream"]["sample_stream_sha256"]
    ):
        raise BodySwayAmplitudeEnvelopeValidationV2Error(
            "Reviewed amplitude v2 sample stream differs from P10.2"
        )


def _require_reviewed_probe_v2(row, report):
    schedule = report["schedule"]
    if row["sample_count"] != schedule["sample_count"] \
            or row["tick_schedule_sha256"] \
                != schedule["tick_schedule_sha256"]:
        raise BodySwayAmplitudeEnvelopeValidationV2Error(
            "Reviewed amplitude v2 schedule differs from P10.2"
        )
    original = {
        check["check_id"]: check for check in report["checks"]
        if check["check_id"] != "sampled_canvas_containment"
    }
    replay = {
        check["check_id"]: check for check in row["checks"]
        if check["check_id"] != "sampled_canvas_containment"
    }
    if _canonical(original) != _canonical(replay):
        raise BodySwayAmplitudeEnvelopeValidationV2Error(
            "Reviewed amplitude v2 non-canvas evidence differs from P10.2"
        )


__all__ = [
    "BodySwayAmplitudeEnvelopeValidationV2Error", "FORMAT_VERSION",
    "body_sway_amplitude_envelope_candidate_sha256_v2",
    "body_sway_amplitude_envelope_probe_sha256_v2",
    "require_body_sway_amplitude_envelope_candidate_v2",
]
