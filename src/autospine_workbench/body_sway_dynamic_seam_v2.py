"""Pure compiler for BodySwayDynamicSeamProbe v2."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .body_sway_dynamic_seam_analysis_v2 import (
    BodySwayDynamicSeamAnalysisV2Error,
    _analyze_admitted_body_sway_dynamic_seam_source_v2,
)
from .body_sway_dynamic_seam_evidence_profile_v2 import (
    CERTIFIED_STATUS,
    FORMAT,
    FORMAT_VERSION,
    body_sway_dynamic_seam_analyzer_profile_v2,
    body_sway_dynamic_seam_release_gate_v2,
)
from .body_sway_dynamic_seam_validation_v2 import (
    BodySwayDynamicSeamSourceV2ValidationError,
    require_body_sway_dynamic_seam_source_v2,
)


Progress = Callable[[str, int, int], None]


class BodySwayDynamicSeamProbeV2Error(ValueError):
    """Raised when exact P10.4b-v2/P10.5c-v1 inputs cannot compile."""


@dataclass(frozen=True, slots=True)
class BodySwayDynamicSeamProbeV2:
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


def compile_body_sway_dynamic_seam_probe_v2(
    raw_source: Mapping[str, Any], *, on_progress: Progress | None = None,
) -> BodySwayDynamicSeamProbeV2:
    """Compile bounded structural evidence without writes or authority."""

    try:
        if on_progress is not None and not callable(on_progress):
            raise BodySwayDynamicSeamProbeV2Error(
                "Dynamic seam probe v2 progress callback is invalid"
            )
        source = require_body_sway_dynamic_seam_source_v2(raw_source)
        analysis = _analyze_admitted_body_sway_dynamic_seam_source_v2(
            source, on_progress=on_progress,
        ).document
        proof = source["body_sway_continuous_preview_proof_v2"]
        certified = analysis["status"] == CERTIFIED_STATUS
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "project_id": proof["project_id"],
            "clip_id": proof["clip_id"],
            "source": source,
            **analysis,
            "analyzer": body_sway_dynamic_seam_analyzer_profile_v2(),
            "release_gate": body_sway_dynamic_seam_release_gate_v2(
                certified
            ),
        }
        return BodySwayDynamicSeamProbeV2(_canonical(document))
    except BodySwayDynamicSeamProbeV2Error:
        raise
    except (
        AttributeError, BodySwayDynamicSeamAnalysisV2Error,
        BodySwayDynamicSeamSourceV2ValidationError, KeyError,
        OverflowError, RecursionError, RuntimeError, TypeError,
        UnicodeError, ValueError,
    ) as exc:
        raise BodySwayDynamicSeamProbeV2Error(
            f"Dynamic seam probe v2 compilation failed: {exc}"
        ) from exc


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))


__all__ = [
    "BodySwayDynamicSeamProbeV2",
    "BodySwayDynamicSeamProbeV2Error",
    "compile_body_sway_dynamic_seam_probe_v2",
]
