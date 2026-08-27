"""Strict public validation for BodySwayDynamicSeamProbe v1."""

from __future__ import annotations

from collections.abc import Mapping
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
from .body_sway_dynamic_seam_profile import (
    MAX_SOURCE_BYTES,
    MAX_SOURCE_JSON_DEPTH,
    MAX_SOURCE_JSON_NODES,
)
from .body_sway_dynamic_seam_source import (
    BodySwayDynamicSeamSourceError,
    require_body_sway_dynamic_seam_source,
)
from .seam_anchor_review_json import (
    canonical_json_bytes,
    require_bounded_json_tree,
)


FORMAT = "autospine-body-sway-dynamic-seam-probe"
FORMAT_VERSION = 1
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


class BodySwayDynamicSeamProbeValidationError(ValueError):
    """Raised when a dynamic seam probe is forged or overclaims."""


def require_body_sway_dynamic_seam_probe(
    document: Mapping[str, Any],
) -> None:
    """Fully replay the source and require exact computed probe evidence."""

    _require_admitted_probe(_bounded_object_copy(document))


def body_sway_dynamic_seam_probe_canonical_bytes(
    document: Mapping[str, Any],
) -> bytes:
    """Return detached canonical bytes only after full semantic replay."""

    root = _bounded_object_copy(document)
    _require_admitted_probe(root)
    return canonical_json_bytes(root)


def body_sway_dynamic_seam_probe_sha256(
    document: Mapping[str, Any],
) -> str:
    """Return the canonical probe identity only after full replay."""

    return hashlib.sha256(
        body_sway_dynamic_seam_probe_canonical_bytes(document)
    ).hexdigest()


def _require_admitted_probe(root: dict[str, Any]) -> None:
    try:
        if set(root) != _TOP_FIELDS:
            raise BodySwayDynamicSeamProbeValidationError(
                "Dynamic seam probe fields are unsupported"
            )
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root["format_version"] != FORMAT_VERSION:
            raise BodySwayDynamicSeamProbeValidationError(
                "Dynamic seam probe format is unsupported"
            )
        raw_source = root.get("source")
        source = require_body_sway_dynamic_seam_source(raw_source)
        if canonical_json_bytes(raw_source) != canonical_json_bytes(source):
            raise BodySwayDynamicSeamProbeValidationError(
                "Dynamic seam probe source differs from exact admission"
            )
        proof = source["body_sway_continuous_preview_proof"]
        if root.get("project_id") != proof["project_id"] \
                or root.get("clip_id") != proof["clip_id"]:
            raise BodySwayDynamicSeamProbeValidationError(
                "Dynamic seam probe project or clip differs from source"
            )
        expected = _analyze_admitted_body_sway_dynamic_seam_source(
            source
        ).document
        actual = {field: root.get(field) for field in _ANALYSIS_FIELDS}
        if canonical_json_bytes(actual) != canonical_json_bytes(expected):
            raise BodySwayDynamicSeamProbeValidationError(
                "Dynamic seam probe evidence differs from exact recomputation"
            )
        if canonical_json_bytes(root.get("analyzer")) \
                != canonical_json_bytes(
                    body_sway_dynamic_seam_analyzer_profile()
                ):
            raise BodySwayDynamicSeamProbeValidationError(
                "Dynamic seam probe analyzer profile is unsupported"
            )
        certified = root["status"] == (
            "continuous_preview_model_reviewed_anchor_proximity_certified"
        )
        if canonical_json_bytes(root.get("release_gate")) \
                != canonical_json_bytes(
                    body_sway_dynamic_seam_release_gate(certified)
                ):
            raise BodySwayDynamicSeamProbeValidationError(
                "Dynamic seam probe release gate must remain blocked"
            )
    except BodySwayDynamicSeamProbeValidationError:
        raise
    except (
        AttributeError, BodySwayDynamicSeamAnalysisError,
        BodySwayDynamicSeamSourceError, KeyError, OverflowError,
        RecursionError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayDynamicSeamProbeValidationError(
            f"Dynamic seam probe validation failed: {exc}"
        ) from exc


def _bounded_object_copy(value: Any) -> dict[str, Any]:
    try:
        require_bounded_json_tree(
            value, max_nodes=MAX_DOCUMENT_JSON_NODES,
            max_depth=MAX_DOCUMENT_JSON_DEPTH,
        )
        encoded = canonical_json_bytes(value)
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise BodySwayDynamicSeamProbeValidationError(
                "Dynamic seam probe exceeds its byte limit"
            )
        copied = json.loads(encoded)
        if type(copied) is not dict:
            raise BodySwayDynamicSeamProbeValidationError(
                "Dynamic seam probe must be an exact JSON object"
            )
        return copied
    except BodySwayDynamicSeamProbeValidationError:
        raise
    except (
        OverflowError, RecursionError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayDynamicSeamProbeValidationError(
            f"Dynamic seam probe JSON is invalid: {exc}"
        ) from exc
