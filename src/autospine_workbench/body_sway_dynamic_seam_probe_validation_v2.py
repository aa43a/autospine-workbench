"""Strict semantic replay for BodySwayDynamicSeamProbe v2."""

from __future__ import annotations

from collections.abc import Callable, Mapping
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
from .body_sway_dynamic_seam_profile_v2 import (
    MAX_SOURCE_BYTES,
    MAX_SOURCE_JSON_DEPTH,
    MAX_SOURCE_JSON_NODES,
)
from .body_sway_dynamic_seam_validation_v2 import (
    BodySwayDynamicSeamSourceV2ValidationError,
    require_body_sway_dynamic_seam_source_v2,
)
from .seam_anchor_review_json import (
    canonical_json_bytes,
    require_bounded_json_tree,
)


Progress = Callable[[str, int, int], None]
MAX_PROBE_OWN_BYTES = 64 * 1024 * 1024
MAX_DOCUMENT_BYTES = MAX_SOURCE_BYTES + MAX_PROBE_OWN_BYTES
MAX_DOCUMENT_JSON_NODES = MAX_SOURCE_JSON_NODES + 1_000_000
MAX_DOCUMENT_JSON_DEPTH = MAX_SOURCE_JSON_DEPTH + 16
_TOP_FIELDS = {
    "format", "format_version", "project_id", "clip_id", "source",
    "problem", "segments", "analyzer", "claims", "status",
    "release_gate", "summary",
}
_ANALYSIS_FIELDS = {"problem", "segments", "claims", "status", "summary"}


class BodySwayDynamicSeamProbeV2ValidationError(ValueError):
    """Raised when a v2 probe is malformed, forged, or overclaims."""


def require_body_sway_dynamic_seam_probe_v2(
    document: Mapping[str, Any], *, on_progress: Progress | None = None,
) -> None:
    """Replay source, interval evidence, analyzer, claims, and gate."""

    try:
        if on_progress is not None and not callable(on_progress):
            raise BodySwayDynamicSeamProbeV2ValidationError(
                "Dynamic seam probe v2 progress callback is invalid"
            )
        root = _bounded_object_copy(document)
        if set(root) != _TOP_FIELDS:
            raise BodySwayDynamicSeamProbeV2ValidationError(
                "Dynamic seam probe v2 fields are unsupported"
            )
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root["format_version"] != FORMAT_VERSION:
            raise BodySwayDynamicSeamProbeV2ValidationError(
                "Dynamic seam probe v2 format is unsupported"
            )
        raw_source = root.get("source")
        source = require_body_sway_dynamic_seam_source_v2(raw_source)
        if canonical_json_bytes(raw_source) != canonical_json_bytes(source):
            raise BodySwayDynamicSeamProbeV2ValidationError(
                "Dynamic seam probe v2 source differs from exact admission"
            )
        proof = source["body_sway_continuous_preview_proof_v2"]
        if root.get("project_id") != proof["project_id"] \
                or root.get("clip_id") != proof["clip_id"]:
            raise BodySwayDynamicSeamProbeV2ValidationError(
                "Dynamic seam probe v2 project or clip differs from source"
            )
        expected = _analyze_admitted_body_sway_dynamic_seam_source_v2(
            source, on_progress=on_progress,
        ).document
        actual = {field: root.get(field) for field in _ANALYSIS_FIELDS}
        if canonical_json_bytes(actual) != canonical_json_bytes(expected):
            raise BodySwayDynamicSeamProbeV2ValidationError(
                "Dynamic seam probe v2 evidence differs from exact replay"
            )
        if canonical_json_bytes(root.get("analyzer")) \
                != canonical_json_bytes(
                    body_sway_dynamic_seam_analyzer_profile_v2()
                ):
            raise BodySwayDynamicSeamProbeV2ValidationError(
                "Dynamic seam probe v2 analyzer profile is unsupported"
            )
        certified = root["status"] == CERTIFIED_STATUS
        if canonical_json_bytes(root.get("release_gate")) \
                != canonical_json_bytes(
                    body_sway_dynamic_seam_release_gate_v2(certified)
                ):
            raise BodySwayDynamicSeamProbeV2ValidationError(
                "Dynamic seam probe v2 release gate must remain blocked"
            )
    except BodySwayDynamicSeamProbeV2ValidationError:
        raise
    except (
        AttributeError, BodySwayDynamicSeamAnalysisV2Error,
        BodySwayDynamicSeamSourceV2ValidationError, KeyError,
        OverflowError, RecursionError, RuntimeError, TypeError,
        UnicodeError, ValueError,
    ) as exc:
        raise BodySwayDynamicSeamProbeV2ValidationError(
            f"Dynamic seam probe v2 validation failed: {exc}"
        ) from exc


def body_sway_dynamic_seam_probe_canonical_bytes_v2(document) -> bytes:
    require_body_sway_dynamic_seam_probe_v2(document)
    return canonical_json_bytes(document)


def body_sway_dynamic_seam_probe_sha256_v2(document) -> str:
    return hashlib.sha256(
        body_sway_dynamic_seam_probe_canonical_bytes_v2(document)
    ).hexdigest()


def _bounded_object_copy(value: Any) -> dict[str, Any]:
    try:
        require_bounded_json_tree(
            value, max_nodes=MAX_DOCUMENT_JSON_NODES,
            max_depth=MAX_DOCUMENT_JSON_DEPTH,
        )
        encoded = canonical_json_bytes(value)
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise BodySwayDynamicSeamProbeV2ValidationError(
                "Dynamic seam probe v2 exceeds its byte limit"
            )
        copied = json.loads(encoded)
        if type(copied) is not dict:
            raise BodySwayDynamicSeamProbeV2ValidationError(
                "Dynamic seam probe v2 must be an exact JSON object"
            )
        return copied
    except BodySwayDynamicSeamProbeV2ValidationError:
        raise
    except (
        OverflowError, RecursionError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayDynamicSeamProbeV2ValidationError(
            f"Dynamic seam probe v2 JSON is invalid: {exc}"
        ) from exc


__all__ = [
    "BodySwayDynamicSeamProbeV2ValidationError",
    "body_sway_dynamic_seam_probe_canonical_bytes_v2",
    "body_sway_dynamic_seam_probe_sha256_v2",
    "require_body_sway_dynamic_seam_probe_v2",
]
