"""Exact admission of one P10.2 report into temporary preview compilation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
from typing import Any

from .body_sway_probe_inputs import BodySwayProbeInputs
from .body_sway_probe_report import (
    BodySwayProbeReportError,
    compile_body_sway_probe_report,
)
from .body_sway_probe_validation import (
    BodySwayProbeValidationError,
    body_sway_probe_report_sha256,
    require_body_sway_probe_report,
)


class BodySwayPreviewInputError(ValueError):
    """Raised when preview inputs are stale, rejected, or not exact snapshots."""


@dataclass(frozen=True, slots=True)
class BodySwayPreviewInputs:
    """Frozen exact probe inputs plus the byte-identical admitted report."""

    _probe_inputs: BodySwayProbeInputs = field(repr=False)
    _report_json: str = field(repr=False)

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


def require_body_sway_preview_inputs(
    probe_inputs: BodySwayProbeInputs,
    report: Mapping[str, Any],
) -> BodySwayPreviewInputs:
    """Recompile P10.2 and admit only its exact non-rejected canonical report."""

    try:
        if type(probe_inputs) is not BodySwayProbeInputs:
            raise BodySwayPreviewInputError(
                "Temporary preview requires exact admitted probe inputs"
            )
        encoded = _canonical(report)
        snapshot = json.loads(encoded)
        if not isinstance(snapshot, dict):
            raise BodySwayPreviewInputError(
                "Body-sway probe report must be a JSON object"
            )
        require_body_sway_probe_report(snapshot)
        rebuilt = compile_body_sway_probe_report(probe_inputs)
        if encoded.encode("utf-8") != rebuilt.canonical_bytes:
            raise BodySwayPreviewInputError(
                "Body-sway probe report differs from exact P3/P5/P9 replay"
            )
        if snapshot["status"] != "manual_visual_required":
            raise BodySwayPreviewInputError(
                "Structurally rejected body sway cannot enter runtime preview"
            )
        value = BodySwayPreviewInputs(probe_inputs, encoded)
        if value.report_sha256 != rebuilt.sha256:
            raise BodySwayPreviewInputError(
                "Body-sway preview report identity is inconsistent"
            )
        return value
    except BodySwayPreviewInputError:
        raise
    except (
        BodySwayProbeReportError, BodySwayProbeValidationError,
        KeyError, OverflowError, RecursionError, TypeError,
        UnicodeError, ValueError,
    ) as exc:
        raise BodySwayPreviewInputError(
            f"Body-sway preview input admission failed: {exc}"
        ) from exc


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
