"""Pure compiler for BodySwayDynamicSeamProbe v1."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .body_sway_dynamic_seam_analysis import (
    BodySwayDynamicSeamAnalysisError,
    _analyze_admitted_body_sway_dynamic_seam_source,
)
from .body_sway_dynamic_seam_evidence_profile import (
    body_sway_dynamic_seam_analyzer_profile,
    body_sway_dynamic_seam_release_gate,
)
from .body_sway_dynamic_seam_source import (
    BodySwayDynamicSeamSourceError,
    require_body_sway_dynamic_seam_source,
)


FORMAT = "autospine-body-sway-dynamic-seam-probe"
FORMAT_VERSION = 1


class BodySwayDynamicSeamProbeError(ValueError):
    """Raised when exact P10.4b2/P10.5c evidence cannot compile a probe."""


@dataclass(frozen=True, slots=True)
class BodySwayDynamicSeamProbe:
    """Frozen path-free dynamic seam evidence and canonical identity."""

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


def compile_body_sway_dynamic_seam_probe(
    raw_source: Mapping[str, Any],
) -> BodySwayDynamicSeamProbe:
    """Compile every adjacent segment without writes or release authority."""

    try:
        source = require_body_sway_dynamic_seam_source(raw_source)
        analysis = _analyze_admitted_body_sway_dynamic_seam_source(
            source
        ).document
        proof = source["body_sway_continuous_preview_proof"]
        certified = analysis["status"] == (
            "continuous_preview_model_reviewed_anchor_proximity_certified"
        )
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "project_id": proof["project_id"],
            "clip_id": proof["clip_id"],
            "source": source,
            **analysis,
            "analyzer": body_sway_dynamic_seam_analyzer_profile(),
            "release_gate": body_sway_dynamic_seam_release_gate(certified),
        }
        return BodySwayDynamicSeamProbe(_canonical(document))
    except BodySwayDynamicSeamProbeError:
        raise
    except (
        AttributeError, BodySwayDynamicSeamAnalysisError,
        BodySwayDynamicSeamSourceError, KeyError, OverflowError,
        RecursionError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayDynamicSeamProbeError(
            f"Dynamic seam probe compilation failed: {exc}"
        ) from exc


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))
