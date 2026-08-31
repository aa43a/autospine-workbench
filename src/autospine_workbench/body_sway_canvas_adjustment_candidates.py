"""Pure P10.2 canvas diagnosis and authority-free adjustment candidates."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .body_sway_canvas_adjustment_candidate_validation import (
    body_sway_canvas_adjustment_candidate_id,
)
from .body_sway_canvas_adjustment_builder import (
    body_sway_canvas_adjustment_source,
    canvas_check_from_report,
    require_reviewed_canvas_probe,
    search_body_sway_canvas_adjustment,
)
from .body_sway_canvas_adjustment_probe import (
    BodySwayCanvasAdjustmentProbeError,
    observe_body_sway_canvas_gain,
    prepare_body_sway_canvas_adjustment_probe,
)
from .capture_framing_envelopes import (
    CaptureFramingEnvelopeSet,
    build_capture_framing_envelope_set,
    setup_capture_envelope,
)
from .body_sway_canvas_adjustment_profile import (
    FORMAT,
    FORMAT_VERSION,
    GAIN_DENOMINATOR,
    SEMANTICS,
    body_sway_canvas_adjustment_analyzer_profile,
    body_sway_canvas_adjustment_release_gate,
    copy_json,
)
from .body_sway_canvas_adjustment_validation import (
    BodySwayCanvasAdjustmentValidationError,
    body_sway_canvas_adjustment_candidates_sha256,
    require_body_sway_canvas_adjustment_candidates,
)
from .body_sway_probe_inputs import BodySwayProbeInputs
from .body_sway_probe_report import (
    BodySwayProbeReport,
    BodySwayProbeReportError,
    compile_body_sway_probe_report,
)
from .idle_behavior_decision_validation import (
    IdleBehaviorDecisionValidationError,
    idle_behavior_decision_sha256,
    require_idle_behavior_decision,
)
from .idle_behavior_review_head import IdleBehaviorReviewHead


class BodySwayCanvasAdjustmentError(ValueError):
    """Raised when exact current evidence cannot form a bounded candidate."""


@dataclass(frozen=True, slots=True)
class BodySwayCanvasAdjustmentCandidates:
    """Canonical candidate document plus its exact reviewed P10.2 report."""

    _canonical_json: str = field(repr=False)
    _reviewed_report: BodySwayProbeReport = field(repr=False)
    _capture_framing_envelopes: CaptureFramingEnvelopeSet | None = field(
        default=None, repr=False,
    )

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()

    @property
    def reviewed_report(self) -> BodySwayProbeReport:
        return self._reviewed_report

    @property
    def capture_framing_envelopes(self) -> CaptureFramingEnvelopeSet | None:
        return self._capture_framing_envelopes


def compile_body_sway_canvas_adjustment_candidates(
    inputs: BodySwayProbeInputs,
    current_head: IdleBehaviorReviewHead,
) -> BodySwayCanvasAdjustmentCandidates:
    """Diagnose the current P10.1 head without writing or approving a revision."""

    try:
        _require_current_head(inputs, current_head)
        report = compile_body_sway_probe_report(inputs)
        report_document = report.document
        reviewed_check = canvas_check_from_report(report_document)
        prepared = prepare_body_sway_canvas_adjustment_probe(inputs)
        if prepared.tick_schedule_sha256 \
                != report_document["schedule"]["tick_schedule_sha256"]:
            raise BodySwayCanvasAdjustmentError(
                "Canvas adjustment schedule differs from exact P10.2"
            )
        reviewed_observation = observe_body_sway_canvas_gain(
            prepared, GAIN_DENOMINATOR, envelope_kind="combined",
        )
        reviewed_probe = reviewed_observation.document
        require_reviewed_canvas_probe(reviewed_check, reviewed_probe)
        probes = [reviewed_probe]
        zero_observation = None
        candidate = None
        if reviewed_check["status"] == "passed":
            classification = "reviewed_canvas_passed"
            reasons = ["reviewed_canvas_containment_passed"]
        else:
            zero_observation = observe_body_sway_canvas_gain(
                prepared, 0, envelope_kind="base",
            )
            zero = zero_observation.document
            probes.append(zero)
            if zero["canvas_status"] == "rejected":
                classification = "upstream_base_motion_canvas_overflow"
                reasons = [
                    "body_sway_zero_gain_did_not_remove_canvas_overflow",
                    "upstream_base_motion_canvas_overflow",
                ]
            else:
                candidate = search_body_sway_canvas_adjustment(
                    inputs.selection, prepared, probes,
                )
                if candidate is None:
                    classification = (
                        "no_nonzero_sampled_adjustment_candidate"
                    )
                    reasons = [
                        "fixed_gain_grid_found_no_nonzero_sampled_pass"
                    ]
                else:
                    classification = (
                        "sampled_adjustment_candidate_available"
                    )
                    reasons = [
                        "lower_uniform_gain_sampled_canvas_and_geometry_passed",
                        "requires_explicit_p10_1_revision",
                    ]
        probes.sort(key=lambda row: row["gain"]["numerator"])
        source = body_sway_canvas_adjustment_source(
            inputs, current_head, report,
        )
        candidates = []
        if candidate is not None:
            candidate["candidate_id"] = (
                body_sway_canvas_adjustment_candidate_id(
                    source, inputs.selection, candidate,
                )
            )
            candidates.append(candidate)
        other_rejections = sorted(
            row["check_id"] for row in report_document["checks"]
            if row["check_id"] != "sampled_canvas_containment"
            and row["status"] == "rejected"
        )
        diagnosis = {
            "classification": classification,
            "reason_codes": sorted(reasons),
            "reviewed_canvas_check": reviewed_check,
            "zero_gain_canvas_status": next((
                row["canvas_status"] for row in probes
                if row["gain"]["numerator"] == 0
            ), "not_evaluated"),
            "other_rejected_check_ids": other_rejections,
        }
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "project_id": inputs.project_id,
            "clip_id": inputs.clip_id,
            "source": source,
            "timing": inputs.timing,
            "reviewed_selection": inputs.selection,
            "analyzer": body_sway_canvas_adjustment_analyzer_profile(),
            "semantics": copy_json(SEMANTICS),
            "diagnosis": diagnosis,
            "probes": probes,
            "adjustment_candidates": candidates,
            "status": "candidate_only",
            "release_gate": body_sway_canvas_adjustment_release_gate(),
            "summary": {
                "classification": classification,
                "tested_gain_count": len(probes),
                "adjustment_candidate_count": len(candidates),
                "reviewed_canvas_failure_tick_count":
                    reviewed_probe["canvas_failure_tick_count"],
                "zero_gain_canvas_failure_tick_count": next((
                    row["canvas_failure_tick_count"] for row in probes
                    if row["gain"]["numerator"] == 0
                ), None),
            },
        }
        require_body_sway_canvas_adjustment_candidates(document)
        framing = None
        if zero_observation is not None \
                and zero_observation.envelope_record is not None \
                and reviewed_observation.envelope_record is not None:
            framing = build_capture_framing_envelope_set(
                setup_capture_envelope(prepared.geometry),
                zero_observation.envelope_record,
                reviewed_observation.envelope_record,
                prepared.geometry.canvas_size[1],
            )
        value = BodySwayCanvasAdjustmentCandidates(
            _canonical(document), report, framing,
        )
        if value.sha256 != body_sway_canvas_adjustment_candidates_sha256(
            value.document
        ):
            raise BodySwayCanvasAdjustmentError(
                "Canvas adjustment candidate identity is inconsistent"
            )
        return value
    except BodySwayCanvasAdjustmentError:
        raise
    except _FAILURES as exc:
        raise BodySwayCanvasAdjustmentError(
            f"Body-sway canvas adjustment failed: {exc}"
        ) from exc


def require_exact_body_sway_canvas_adjustment_candidates(
    inputs: BodySwayProbeInputs,
    current_head: IdleBehaviorReviewHead,
    document: Mapping[str, Any],
) -> str:
    """Recompile exact current evidence and reject a changed candidate byte."""

    try:
        supplied = _canonical(document).encode("utf-8")
        expected = compile_body_sway_canvas_adjustment_candidates(
            inputs, current_head,
        )
        if supplied != expected.canonical_bytes:
            raise BodySwayCanvasAdjustmentError(
                "Canvas adjustment candidate differs from exact replay"
            )
        return expected.sha256
    except BodySwayCanvasAdjustmentError:
        raise
    except (OverflowError, TypeError, UnicodeError, ValueError) as exc:
        raise BodySwayCanvasAdjustmentError(
            f"Exact canvas adjustment replay failed: {exc}"
        ) from exc


def _require_current_head(inputs, head):
    if type(inputs) is not BodySwayProbeInputs \
            or type(head) is not IdleBehaviorReviewHead \
            or head.decision is None:
        raise BodySwayCanvasAdjustmentError(
            "Canvas adjustment requires one exact current P10.1 decision"
        )
    decision = inputs.decision
    require_idle_behavior_decision(decision)
    digest = idle_behavior_decision_sha256(decision)
    source = inputs.source
    if head.decision.document != decision or head.decision_sha256 != digest \
            or source["idle_behavior_decision_sha256"] != digest \
            or source["idle_behavior_candidates_sha256"] \
            != decision["source"]["idle_behavior_candidates_sha256"] \
            or head.current_revision != decision["review"]["revision"]:
        raise BodySwayCanvasAdjustmentError(
            "Canvas adjustment P10.1 current head binding is stale"
        )


def _canonical(value) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )


_FAILURES = (
    AttributeError, BodySwayCanvasAdjustmentProbeError,
    BodySwayCanvasAdjustmentValidationError, BodySwayProbeReportError,
    IdleBehaviorDecisionValidationError, KeyError, OverflowError,
    StopIteration, TypeError, UnicodeError, ValueError,
)
