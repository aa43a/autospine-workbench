"""Pure compiler for the P10.2b CaptureFramingCandidate v1 contract."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .body_sway_probe_inputs import BodySwayProbeInputs
from .body_sway_probe_report import BodySwayProbeReport
from .capture_framing_geometry import (
    CaptureFramingGeometryError,
    contains_with_capture_margin,
    proposed_runtime_world_viewport,
    sample_capture_envelopes,
)
from .capture_framing_envelopes import CaptureFramingEnvelopeSet
from .capture_framing_profile import (
    CANDIDATE_RELEASE_GATE,
    CANDIDATE_SEMANTICS,
    CAPTURE_VIEWPORT,
    COORDINATE_TRANSFORM_ID,
    ENVELOPE_KINDS,
    FORMAT,
    FORMAT_VERSION,
    capture_framing_profile,
)
from .dynamic_viewport_fit import DynamicViewportFit
from .idle_behavior_review_head import IdleBehaviorReviewHead
from .manifest_artifacts import require_sha256
from .resolved_project import canonical_sha256


class CaptureFramingCandidateError(ValueError):
    """Raised when exact P10.2 evidence cannot form a framing candidate."""


@dataclass(frozen=True, slots=True)
class CaptureFramingCandidate:
    _canonical_json: str = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


def compile_capture_framing_candidate(
    inputs: BodySwayProbeInputs,
    report: BodySwayProbeReport,
    dynamic_viewport: DynamicViewportFit,
    head: IdleBehaviorReviewHead,
    *, package_id: str,
    envelope_set: CaptureFramingEnvelopeSet | None = None,
) -> CaptureFramingCandidate:
    """Compile setup/base/combined envelopes and one zero-authority draft."""

    try:
        package = require_sha256(package_id, "Capture framing package")
        _require_inputs(inputs, report, dynamic_viewport, head)
        if envelope_set is None:
            envelope_set = sample_capture_envelopes(inputs, report)
        if type(envelope_set) is not CaptureFramingEnvelopeSet:
            raise CaptureFramingCandidateError(
                "Capture framing envelope evidence is invalid"
            )
        envelope_document = envelope_set.document
        envelopes = envelope_document["envelopes"]
        union_canvas = envelope_document["union_envelope_canvas"]
        union_runtime = envelope_document["union_envelope_runtime"]
        witnesses = envelope_document["union_extrema_witnesses"]
        canvas_height = envelope_document["canvas_height"]
        world = proposed_runtime_world_viewport(union_runtime)
        profile = capture_framing_profile()
        profile_sha = canonical_sha256(profile)
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "project_id": inputs.project_id,
            "clip_id": inputs.clip_id,
            "source": {
                "package_id": package,
                "body_sway_probe_report_sha256": report.sha256,
                "dynamic_viewport_fit_sha256": dynamic_viewport.sha256,
                "tick_schedule_sha256": report.document[
                    "schedule"
                ]["tick_schedule_sha256"],
                "current_p10_1_head": {
                    "candidate_sha256": inputs.source[
                        "idle_behavior_candidates_sha256"
                    ],
                    "decision_sha256": head.decision_sha256,
                    "revision": head.current_revision,
                },
                "capture_framing_profile_sha256": profile_sha,
                "layer_manifest_sha256": inputs.source[
                    "layer_manifest_sha256"
                ],
                "p3": inputs.source["p3"],
                "p5": inputs.source["p5"],
                "p9": inputs.source["p9"],
            },
            "timing": inputs.timing,
            "coordinate_spaces": {
                "envelope_space": "rig-canvas-top-left-y-down",
                "world_viewport_space": "spine-world-bottom-left-y-up",
                "canvas_height": canvas_height,
                "transform_id": COORDINATE_TRANSFORM_ID,
            },
            "envelopes": envelopes,
            "union_envelope_canvas": union_canvas,
            "union_envelope_runtime": union_runtime,
            "union_extrema_witnesses": witnesses,
            "capture_viewport": _copy(CAPTURE_VIEWPORT),
            "proposed_world_viewport": world,
            "coverage": {
                kind: contains_with_capture_margin(
                    world, envelopes[kind]["bounds_runtime"], CAPTURE_VIEWPORT,
                )
                for kind in ENVELOPE_KINDS
            },
            "compiler": profile,
            "compiler_sha256": profile_sha,
            "semantics": _copy(CANDIDATE_SEMANTICS),
            "status": "candidate_only",
            "release_gate": _copy(CANDIDATE_RELEASE_GATE),
        }
        from .capture_framing_validation import require_capture_framing_candidate
        require_capture_framing_candidate(document)
        return CaptureFramingCandidate(_canonical(document))
    except CaptureFramingCandidateError:
        raise
    except (
        CaptureFramingGeometryError, KeyError, OverflowError,
        RecursionError, TypeError,
        UnicodeError, ValueError,
    ) as exc:
        raise CaptureFramingCandidateError(
            f"Capture framing candidate compilation failed: {exc}"
        ) from exc


def require_exact_capture_framing_candidate(
    inputs, report, viewport, head, value, *, package_id,
):
    expected = compile_capture_framing_candidate(
        inputs, report, viewport, head, package_id=package_id,
    )
    if _canonical(value).encode("utf-8") != expected.canonical_bytes:
        raise CaptureFramingCandidateError(
            "Capture framing candidate differs from exact P10.2 replay"
        )
    return expected.sha256


def _require_inputs(inputs, report, viewport, head):
    if type(inputs) is not BodySwayProbeInputs \
            or type(report) is not BodySwayProbeReport \
            or type(viewport) is not DynamicViewportFit \
            or type(head) is not IdleBehaviorReviewHead:
        raise CaptureFramingCandidateError(
            "Capture framing requires exact P10.2 values"
        )
    document = report.document
    rejected = sorted(
        row["check_id"] for row in document["checks"]
        if row["status"] == "rejected"
    )
    if document["status"] != "structural_rejected" \
            or rejected != ["sampled_canvas_containment"] \
            or viewport.document["fit_status"] != "fitted":
        raise CaptureFramingCandidateError(
            "Capture framing is only available for an exact canvas-only reject"
        )
    source = document["source"]
    if source != inputs.source \
            or head.current_revision < 1 \
            or head.decision_sha256 != source["idle_behavior_decision_sha256"]:
        raise CaptureFramingCandidateError(
            "Capture framing source differs from the current P10.1 head"
        )


def _copy(value: Any) -> Any:
    return json.loads(_canonical(value))


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))
