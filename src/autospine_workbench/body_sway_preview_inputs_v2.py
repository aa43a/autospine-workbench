"""Exact P10.2b admission for capture-framed temporary preview v2."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .body_sway_probe_evidence_validation import CHECK_ORDER
from .body_sway_probe_inputs import BodySwayProbeInputs
from .body_sway_probe_report import (
    BodySwayProbeReport,
    BodySwayProbeReportError,
    compile_body_sway_probe_report,
)
from .body_sway_probe_validation import (
    BodySwayProbeValidationError,
    body_sway_probe_report_sha256,
)
from .body_sway_preview_inputs import BodySwayPreviewInputs
from .body_sway_remediation_analysis import (
    BodySwayRemediationAnalysisError,
    compile_body_sway_remediation_analysis,
)
from .capture_framing_candidate import (
    CaptureFramingCandidate,
    CaptureFramingCandidateError,
    require_exact_capture_framing_candidate,
)
from .capture_framing_decision import CaptureFramingDecision
from .capture_framing_history import CaptureFramingHistorySnapshot
from .capture_framing_validation import (
    CaptureFramingValidationError,
    require_capture_world_viewport,
)
from .capture_framing_verified_head import (
    CaptureFramingVerifiedHeadError,
    read_capture_framing_verified_head,
    same_capture_framing_verified_head,
)
from .idle_behavior_review_head import (
    IdleBehaviorReviewHeadError,
    read_idle_behavior_review_head,
    same_idle_behavior_review_head,
)


class BodySwayPreviewInputV2Error(ValueError):
    """Raised when capture-framed P10.3 v2 inputs are stale or inexact."""


@dataclass(frozen=True, slots=True)
class BodySwayPreviewInputsV2:
    """Frozen exact P10.2 evidence plus current approved framing authority."""

    _probe_inputs: BodySwayProbeInputs = field(repr=False)
    _report_json: str = field(repr=False)
    _candidate_json: str = field(repr=False)
    _decision_json: str = field(repr=False)
    _history: CaptureFramingHistorySnapshot = field(repr=False)

    @property
    def project_id(self) -> str:
        return self._probe_inputs.project_id

    @property
    def clip_id(self) -> str:
        return self._probe_inputs.clip_id

    @property
    def probe_inputs(self) -> BodySwayProbeInputs:
        return self._probe_inputs

    @property
    def report(self) -> dict[str, Any]:
        return json.loads(self._report_json)

    @property
    def report_sha256(self) -> str:
        return body_sway_probe_report_sha256(self.report)

    @property
    def source(self) -> dict[str, Any]:
        return self.report["source"]

    @property
    def timing(self) -> dict[str, Any]:
        return self.report["timing"]

    @property
    def selection(self) -> dict[str, Any]:
        return self.report["selection"]

    @property
    def framing_candidate(self) -> dict[str, Any]:
        return json.loads(self._candidate_json)

    @property
    def framing_candidate_sha256(self) -> str:
        return CaptureFramingCandidate(self._candidate_json).sha256

    @property
    def framing_decision(self) -> dict[str, Any]:
        return json.loads(self._decision_json)

    @property
    def framing_decision_sha256(self) -> str:
        return CaptureFramingDecision(self._decision_json).sha256

    @property
    def framing_revision(self) -> int:
        return self._history.current_revision

    @property
    def world_viewport(self) -> dict[str, Any]:
        return dict(self.framing_decision["decision"]["world_viewport"])

    def legacy_projection_inputs(self) -> BodySwayPreviewInputs:
        """Return a math-only adapter; this does not invoke v1 admission."""

        return BodySwayPreviewInputs(self._probe_inputs, self._report_json)


def require_body_sway_preview_inputs_v2(
    probe_inputs: BodySwayProbeInputs,
    report: BodySwayProbeReport,
    candidate: CaptureFramingCandidate,
    decision: CaptureFramingDecision,
    history: CaptureFramingHistorySnapshot,
    *,
    state_root: Path,
    package_id: str,
) -> BodySwayPreviewInputsV2:
    """Replay all evidence and admit only the unchanged current framing head."""

    try:
        _require_types(probe_inputs, report, candidate, decision, history)
        rebuilt = compile_body_sway_probe_report(probe_inputs)
        if report.canonical_bytes != rebuilt.canonical_bytes:
            raise BodySwayPreviewInputV2Error(
                "Body-sway report differs from exact P3/P5/P9 replay"
            )
        _require_canvas_only_reject(rebuilt.document)
        p10_head = read_idle_behavior_review_head(
            state_root, probe_inputs.candidates,
        )
        _require_current_p10_1(probe_inputs, p10_head)
        viewport = compile_body_sway_remediation_analysis(
            probe_inputs, rebuilt,
        ).dynamic_viewport
        require_exact_capture_framing_candidate(
            probe_inputs, rebuilt, viewport, p10_head,
            candidate.document, package_id=package_id,
        )
        current = read_capture_framing_verified_head(state_root, candidate)
        if current.snapshot != history \
                or current.decision is None \
                or current.decision.canonical_bytes != decision.canonical_bytes:
            raise BodySwayPreviewInputV2Error(
                "Capture framing decision is not the exact current head"
            )
        _require_ready_decision(candidate, decision, history)
        p10_after = read_idle_behavior_review_head(
            state_root, probe_inputs.candidates,
        )
        framing_after = read_capture_framing_verified_head(
            state_root, candidate,
        )
        if not same_idle_behavior_review_head(p10_head, p10_after) \
                or not same_capture_framing_verified_head(
                    current, framing_after,
                ):
            raise BodySwayPreviewInputV2Error(
                "P10.1 or capture framing head changed during v2 admission"
            )
        return BodySwayPreviewInputsV2(
            probe_inputs, rebuilt.canonical_bytes.decode("utf-8"),
            candidate.canonical_bytes.decode("utf-8"),
            decision.canonical_bytes.decode("utf-8"), history,
        )
    except BodySwayPreviewInputV2Error:
        raise
    except (
        BodySwayProbeReportError, BodySwayProbeValidationError,
        BodySwayRemediationAnalysisError, CaptureFramingCandidateError,
        CaptureFramingValidationError, CaptureFramingVerifiedHeadError,
        IdleBehaviorReviewHeadError,
        AttributeError, KeyError, OSError, OverflowError, RecursionError,
        RuntimeError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayPreviewInputV2Error(
            f"Body-sway preview v2 admission failed: {exc}"
        ) from exc


def _require_types(inputs, report, candidate, decision, history):
    if type(inputs) is not BodySwayProbeInputs \
            or type(report) is not BodySwayProbeReport \
            or type(candidate) is not CaptureFramingCandidate \
            or type(decision) is not CaptureFramingDecision \
            or type(history) is not CaptureFramingHistorySnapshot:
        raise BodySwayPreviewInputV2Error(
            "Temporary preview v2 requires exact admitted values"
        )


def _require_canvas_only_reject(document):
    rejected = {
        row["check_id"] for row in document["checks"]
        if row["status"] == "rejected"
    }
    if document["status"] != "structural_rejected" \
            or rejected != {"sampled_canvas_containment"}:
        raise BodySwayPreviewInputV2Error(
            "Preview v2 requires an exact canvas-containment-only reject"
        )
    structural = set(CHECK_ORDER[:5]) - {"sampled_canvas_containment"}
    if any(row["status"] == "rejected" and row["check_id"] in structural
           for row in document["checks"]):
        raise BodySwayPreviewInputV2Error(
            "A non-canvas structural check rejected the motion"
        )


def _require_current_p10_1(inputs, head):
    decision = head.decision
    if decision is None or head.current_revision < 1 \
            or head.decision_sha256 \
            != inputs.source["idle_behavior_decision_sha256"] \
            or decision.document != inputs.decision:
        raise BodySwayPreviewInputV2Error(
            "Body-sway inputs are not bound to the current P10.1 head"
        )


def _require_ready_decision(candidate, decision, history):
    document = decision.document
    action = document["decision"]["action"]
    viewport = document["decision"]["world_viewport"]
    if action not in {"accept", "adjust"} \
            or document["status"] != "ready_for_temporary_preview_v2" \
            or document["source"]["capture_framing_candidate_sha256"] \
            != candidate.sha256 \
            or history.head_decision_sha256 != decision.sha256 \
            or history.current_revision != document["review"]["revision"] \
            or history.action != action \
            or history.status != document["status"] \
            or viewport != require_body_sway_preview_world_viewport_v2(
                candidate, viewport,
            ):
        raise BodySwayPreviewInputV2Error(
            "Capture framing head is not ready for temporary preview v2"
        )


def require_body_sway_preview_world_viewport_v2(candidate, viewport):
    """Reuse the bounded P10.2b viewport contract for Preview v2."""

    if type(candidate) is not CaptureFramingCandidate:
        raise BodySwayPreviewInputV2Error(
            "Preview v2 world viewport requires an exact framing candidate"
        )
    document = candidate.document
    return require_capture_world_viewport(
        viewport,
        union=document["union_envelope_runtime"],
        capture_viewport=document["capture_viewport"],
    )
