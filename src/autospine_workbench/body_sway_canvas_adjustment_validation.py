"""Strict standalone validation for sampled canvas-adjustment candidates."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .body_sway_canvas_adjustment_profile import (
    FORMAT,
    FORMAT_VERSION,
    SEMANTICS,
    body_sway_canvas_adjustment_analyzer_profile,
    body_sway_canvas_adjustment_release_gate,
)
from .body_sway_canvas_adjustment_candidate_validation import (
    BodySwayCanvasAdjustmentCandidateFieldError,
    require_adjustment_candidates,
)
from .body_sway_canvas_adjustment_probe_validation import (
    BodySwayCanvasAdjustmentProbeFieldError,
    require_diagnosis,
    require_probe_rows,
    require_summary,
)
from .body_sway_probe_validation import (
    require_body_sway_selection,
    require_body_sway_source,
)
from .idle_behavior_decision_validation_fields import (
    digest_value,
    exact_fields,
    identifier_value,
    object_value,
    require_timing,
)
from .idle_behavior_review_profile import MAX_REVISIONS
from .resolved_project import canonical_sha256


MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
_TOP = {
    "format", "format_version", "project_id", "clip_id", "source",
    "timing", "reviewed_selection", "analyzer", "semantics",
    "diagnosis", "probes", "adjustment_candidates", "status",
    "release_gate", "summary",
}


class BodySwayCanvasAdjustmentValidationError(ValueError):
    """Raised when a candidate document overclaims or is inconsistent."""


def require_body_sway_canvas_adjustment_candidates(
    document: Mapping[str, Any],
) -> None:
    """Validate shape, derivations, bounded evidence, and zero authority."""

    try:
        root = object_value(document, "Canvas adjustment candidates")
        exact_fields(root, _TOP, "Canvas adjustment candidates")
        if root.get("format") != FORMAT \
                or root.get("format_version") != FORMAT_VERSION:
            raise BodySwayCanvasAdjustmentValidationError(
                "Canvas adjustment candidate format is unsupported"
            )
        identifier_value(root.get("project_id"), "project_id")
        identifier_value(root.get("clip_id"), "clip_id")
        source = _source(root.get("source"))
        require_timing(root.get("timing"))
        require_body_sway_selection(root.get("reviewed_selection"))
        _fixed(root.get("analyzer"),
               body_sway_canvas_adjustment_analyzer_profile(), "analyzer")
        _fixed(root.get("semantics"), SEMANTICS, "semantics")
        probes = require_probe_rows(root.get("probes"), root["timing"])
        candidates = require_adjustment_candidates(root, source, probes)
        classification = require_diagnosis(root.get("diagnosis"), probes)
        if root.get("status") != "candidate_only":
            raise BodySwayCanvasAdjustmentValidationError(
                "Canvas adjustment result must remain candidate-only"
            )
        _fixed(root.get("release_gate"),
               body_sway_canvas_adjustment_release_gate(), "release gate")
        require_summary(
            root.get("summary"), classification, probes, candidates,
        )
        if len(_canonical(root)) > MAX_DOCUMENT_BYTES:
            raise BodySwayCanvasAdjustmentValidationError(
                "Canvas adjustment candidate document is too large"
            )
    except BodySwayCanvasAdjustmentValidationError:
        raise
    except (BodySwayCanvasAdjustmentCandidateFieldError,
            BodySwayCanvasAdjustmentProbeFieldError, KeyError,
            OverflowError, TypeError, UnicodeError, ValueError) as exc:
        raise BodySwayCanvasAdjustmentValidationError(
            f"Canvas adjustment candidate validation failed: {exc}"
        ) from exc


def body_sway_canvas_adjustment_candidates_sha256(
    document: Mapping[str, Any],
) -> str:
    """Return the canonical identity only after strict validation."""

    require_body_sway_canvas_adjustment_candidates(document)
    return canonical_sha256(document)


def _source(value):
    source = object_value(value, "Canvas adjustment source")
    exact_fields(source, {
        "probe_inputs", "current_p10_1_head",
        "body_sway_probe_report_sha256",
    }, "Canvas adjustment source")
    require_body_sway_source(source.get("probe_inputs"))
    digest_value(source.get("body_sway_probe_report_sha256"), "probe report")
    head = object_value(source.get("current_p10_1_head"), "P10.1 head")
    exact_fields(head, {
        "candidate_sha256", "decision_sha256", "revision",
    }, "P10.1 head")
    digest_value(head.get("candidate_sha256"), "P10.1 candidate")
    digest_value(head.get("decision_sha256"), "P10.1 decision")
    if type(head.get("revision")) is not int \
            or not 1 <= head["revision"] <= MAX_REVISIONS \
            or head["candidate_sha256"] \
            != source["probe_inputs"]["idle_behavior_candidates_sha256"] \
            or head["decision_sha256"] \
            != source["probe_inputs"]["idle_behavior_decision_sha256"]:
        raise BodySwayCanvasAdjustmentValidationError(
            "Canvas adjustment current head binding is inconsistent"
        )
    return source


def _fixed(value, expected, label):
    if value != expected:
        raise BodySwayCanvasAdjustmentValidationError(
            f"Canvas adjustment {label} differs from its profile"
        )


def _canonical(value) -> bytes:
    return json.dumps(
        dict(value) if isinstance(value, Mapping) else value,
        ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
