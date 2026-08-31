"""Immutable cached value for exact P10.2 derived diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any

from .body_sway_canvas_adjustment_candidates import (
    BodySwayCanvasAdjustmentCandidates,
)
from .body_sway_probe_report import BodySwayProbeReport
from .capture_framing_candidate import CaptureFramingCandidate
from .dynamic_viewport_fit import DynamicViewportFit
from .region_rebind_candidates import RegionRebindCandidateArtifact


class BodySwayDerivedValueError(RuntimeError):
    """Raised when a derived value cannot be frozen safely."""


@dataclass(frozen=True, slots=True)
class BodySwayDerivedResult:
    """JSON-frozen derived values whose accessors return detached objects."""

    _adjustment_json: str = field(repr=False)
    _report_json: str = field(repr=False)
    _preview_json: str = field(repr=False)
    _dynamic_viewport_json: str | None = field(default=None, repr=False)
    _rebind_json: tuple[str, ...] = field(default=(), repr=False)
    _capture_framing_json: str | None = field(default=None, repr=False)

    @classmethod
    def freeze(
        cls,
        adjustment: BodySwayCanvasAdjustmentCandidates,
        preview: dict[str, Any],
        dynamic_viewport: DynamicViewportFit | None = None,
        rebind_candidates: tuple[RegionRebindCandidateArtifact, ...] = (),
        capture_framing: CaptureFramingCandidate | None = None,
    ) -> BodySwayDerivedResult:
        if type(adjustment) is not BodySwayCanvasAdjustmentCandidates \
                or type(adjustment.reviewed_report) is not BodySwayProbeReport \
                or type(preview) is not dict \
                or dynamic_viewport is not None \
                and type(dynamic_viewport) is not DynamicViewportFit \
                or type(rebind_candidates) is not tuple \
                or any(type(row) is not RegionRebindCandidateArtifact
                       for row in rebind_candidates) \
                or capture_framing is not None \
                and type(capture_framing) is not CaptureFramingCandidate:
            raise BodySwayDerivedValueError(
                "P10.2 derived compiler returned an unsupported value"
            )
        return cls(
            adjustment.canonical_bytes.decode("utf-8"),
            adjustment.reviewed_report.canonical_bytes.decode("utf-8"),
            _canonical(preview),
            dynamic_viewport.canonical_bytes.decode("utf-8")
            if dynamic_viewport is not None else None,
            tuple(_canonical(row.document) for row in rebind_candidates),
            capture_framing.canonical_bytes.decode("utf-8")
            if capture_framing is not None else None,
        )

    @property
    def canvas_adjustment(self) -> BodySwayCanvasAdjustmentCandidates:
        report = BodySwayProbeReport(self._report_json)
        return BodySwayCanvasAdjustmentCandidates(
            self._adjustment_json, report,
        )

    @property
    def preview(self) -> dict[str, Any]:
        return json.loads(self._preview_json)

    @property
    def dynamic_viewport(self) -> DynamicViewportFit | None:
        if self._dynamic_viewport_json is None:
            return None
        return DynamicViewportFit(self._dynamic_viewport_json)

    @property
    def rebind_candidates(self) -> tuple[RegionRebindCandidateArtifact, ...]:
        return tuple(
            RegionRebindCandidateArtifact(value)
            for value in self._rebind_json
        )

    @property
    def capture_framing(self) -> CaptureFramingCandidate | None:
        if self._capture_framing_json is None:
            return None
        return CaptureFramingCandidate(self._capture_framing_json)

    @property
    def cache_weight_bytes(self) -> int:
        values = (
            self._adjustment_json, self._report_json, self._preview_json,
            self._dynamic_viewport_json, *self._rebind_json,
            self._capture_framing_json,
        )
        return sum(
            len(value.encode("utf-8")) for value in values
            if value is not None
        )


def _canonical(value: Any) -> str:
    try:
        return json.dumps(
            value, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        )
    except (OverflowError, TypeError, UnicodeError, ValueError) as exc:
        raise BodySwayDerivedValueError(
            "P10.2 derived cache value is not canonical JSON"
        ) from exc
