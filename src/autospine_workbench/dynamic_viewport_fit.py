"""Deterministic, authority-free fitting of a sampled motion envelope."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .dynamic_viewport_fit_inputs import (
    DynamicViewportFitInputError,
    MAX_GEOMETRY_ITEM_COUNT,
    MAX_POINT_COUNT,
    MAX_SAMPLE_COUNT,
    NUMERIC_PRECISION_DECIMALS,
    envelope_value,
    normalize_dynamic_viewport_inputs,
    quantize,
)


FORMAT = "autospine-dynamic-viewport-fit"
FORMAT_VERSION = 1
PROFILE_ID = "dynamic-viewport-fit"
PROFILE_VERSION = "1.0.0"
FIT_TOLERANCE_PX = 1e-6

SEMANTICS = {
    "scope": "dynamic-viewport-fit-candidate-only",
    "authority": "none",
    "source_canvas_containment_required": False,
    "source_canvas_overflow_is_rig_structural_failure": False,
    "rig_binding_changed": False,
    "human_decision_emitted": False,
    "review_revision_written": False,
    "visual_quality_claimed": False,
    "continuous_time_safety_claimed": False,
    "runtime_equivalence_claimed": False,
    "release_authority_claimed": False,
}

RELEASE_GATE = {
    "status": "blocked",
    "reason_codes": [
        "candidate_has_no_review_authority",
        "sampled_envelope_is_not_continuous_time_proof",
        "runtime_visual_review_required",
    ],
}


class DynamicViewportFitError(ValueError):
    """Raised when finite geometry cannot form an exact viewport candidate."""


@dataclass(frozen=True, slots=True)
class DynamicViewportFit:
    """Canonical fit document detached from caller-owned input objects."""

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


def compile_dynamic_viewport_fit(
    *, sampled_geometry=None, point_bounds=None,
    output_viewport: Mapping[str, Any], margin_px: Any = 0,
) -> DynamicViewportFit:
    """Fit exactly one sampled-geometry or generic-bounds evidence source."""

    try:
        source, envelope, viewport, margin = normalize_dynamic_viewport_inputs(
            sampled_geometry, point_bounds, output_viewport, margin_px,
        )
        derived = derive_dynamic_viewport_fit(envelope, viewport, margin)
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "source": source,
            "viewport": viewport,
            "margin_px": margin,
            "motion_envelope": envelope,
            **derived,
            "profile": dynamic_viewport_fit_profile(),
            "semantics": _copy(SEMANTICS),
            "status": "candidate_only",
            "release_gate": _copy(RELEASE_GATE),
        }
        from .dynamic_viewport_fit_validation import require_dynamic_viewport_fit
        require_dynamic_viewport_fit(document)
        return DynamicViewportFit(_canonical(document))
    except DynamicViewportFitError:
        raise
    except (DynamicViewportFitInputError, KeyError, OverflowError,
            TypeError, UnicodeError, ValueError) as exc:
        raise DynamicViewportFitError(f"Dynamic viewport fit failed: {exc}") from exc


def require_exact_dynamic_viewport_fit(
    document: Mapping[str, Any], *, sampled_geometry=None, point_bounds=None,
    output_viewport: Mapping[str, Any], margin_px: Any = 0,
) -> str:
    """Recompile supplied evidence and reject any changed result byte."""

    expected = compile_dynamic_viewport_fit(
        sampled_geometry=sampled_geometry, point_bounds=point_bounds,
        output_viewport=output_viewport, margin_px=margin_px,
    )
    try:
        supplied = _canonical(document).encode("utf-8")
    except (OverflowError, TypeError, UnicodeError, ValueError) as exc:
        raise DynamicViewportFitError(
            f"Exact dynamic viewport replay failed: {exc}"
        ) from exc
    if supplied != expected.canonical_bytes:
        raise DynamicViewportFitError(
            "Dynamic viewport fit differs from exact replay"
        )
    return expected.sha256


def dynamic_viewport_fit_profile() -> dict[str, Any]:
    return {
        "id": PROFILE_ID,
        "version": PROFILE_VERSION,
        "config": {
            "transform": "output_xy=source_xy*uniform_scale+translation_xy",
            "scale_policy": "free-uniform-contain-and-center",
            "numeric_precision_decimals": NUMERIC_PRECISION_DECIMALS,
            "fit_tolerance_px": FIT_TOLERANCE_PX,
            "max_sample_count": MAX_SAMPLE_COUNT,
            "max_geometry_item_count": MAX_GEOMETRY_ITEM_COUNT,
            "max_point_count": MAX_POINT_COUNT,
        },
    }


def derive_dynamic_viewport_fit(envelope, viewport, margin):
    """Derive the pinned uniform transform from normalized finite fields."""

    min_x, min_y = envelope["min_xy"]
    max_x, max_y = envelope["max_xy"]
    width, height = envelope["size"]
    inner_w = viewport["width"] - margin["left"] - margin["right"]
    inner_h = viewport["height"] - margin["top"] - margin["bottom"]
    ratios = []
    if width > 0.0:
        ratios.append(inner_w / width)
    if height > 0.0:
        ratios.append(inner_h / height)
    scale = quantize(min(ratios) if ratios else 1.0)
    if not 0.0 < scale <= 1e15:
        raise DynamicViewportFitError("Dynamic viewport scale is invalid")
    center_x = margin["left"] + inner_w / 2.0
    center_y = margin["top"] + inner_h / 2.0
    source_cx, source_cy = envelope["center_xy"]
    translation = [quantize(center_x - source_cx * scale),
                   quantize(center_y - source_cy * scale)]
    fitted = envelope_value([
        [quantize(min_x * scale + translation[0]),
         quantize(min_y * scale + translation[1])],
        [quantize(max_x * scale + translation[0]),
         quantize(max_y * scale + translation[1])],
    ])
    status = "fitted" if _contains(fitted, viewport, margin) else "indeterminate"
    return {
        "transform": {
            "uniform_scale": scale,
            "translation_xy": translation,
            "equation": "output_xy=source_xy*uniform_scale+translation_xy",
        },
        "fitted_envelope": fitted,
        "fit_status": status,
    }


def _contains(envelope, viewport, margin):
    tolerance = FIT_TOLERANCE_PX
    return envelope["min_xy"][0] >= margin["left"] - tolerance \
        and envelope["min_xy"][1] >= margin["top"] - tolerance \
        and envelope["max_xy"][0] <= viewport["width"] - margin["right"] + tolerance \
        and envelope["max_xy"][1] <= viewport["height"] - margin["bottom"] + tolerance


def _copy(value):
    return json.loads(_canonical(value))


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))
