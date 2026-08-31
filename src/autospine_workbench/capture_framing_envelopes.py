"""Streaming tri-domain envelope evidence for P10.2b capture framing."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from typing import Any

from .capture_framing_profile import (
    CAPTURE_VIEWPORT,
    ENVELOPE_KINDS,
    NUMERIC_PRECISION_DECIMALS,
)
from .dynamic_viewport_fit_inputs import envelope_value


MAX_SAMPLES = 4096
MAX_ATTACHMENT_SAMPLES = 262_144
MAX_POINTS = 2_000_000


class CaptureFramingEnvelopeError(ValueError):
    """Raised when streamed framing geometry is empty or excessive."""


@dataclass(frozen=True, slots=True)
class CaptureFramingEnvelopeSet:
    _canonical_json: str = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)


@dataclass(slots=True)
class CaptureEnvelopeAccumulator:
    """Bounded deterministic extrema and evidence digest accumulator."""

    kind: str
    canvas_height: float
    _digest: Any = field(init=False, repr=False)
    _ticks: set[int] = field(default_factory=set, init=False, repr=False)
    _sample_count: int = field(default=0, init=False)
    _attachment_count: int = field(default=0, init=False)
    _point_count: int = field(default=0, init=False)
    _extrema: dict[str, tuple[Any, ...]] = field(
        default_factory=dict, init=False, repr=False,
    )

    def __post_init__(self):
        if not isinstance(self.kind, str) or not self.kind \
                or not math.isfinite(float(self.canvas_height)) \
                or self.canvas_height <= 0:
            raise CaptureFramingEnvelopeError("Framing accumulator is invalid")
        self.canvas_height = _q(self.canvas_height)
        self._digest = hashlib.sha256()
        _feed(self._digest, {
            "domain": "autospine-capture-framing-envelope/v1",
            "kind": self.kind,
        })

    def observe(self, tick: int, attachments) -> None:
        if type(tick) is not int or tick < 0 or tick in self._ticks:
            raise CaptureFramingEnvelopeError("Framing sample tick is invalid")
        rows = []
        for attachment_id, raw_points in sorted(
            attachments, key=lambda item: item[0]
        ):
            points = [_point(point) for point in raw_points]
            if not isinstance(attachment_id, str) or not attachment_id \
                    or not points:
                raise CaptureFramingEnvelopeError(
                    "Framing attachment geometry is invalid"
                )
            rows.append({
                "attachment_id": attachment_id,
                "posed_vertices_xy": points,
            })
            for index, point in enumerate(points):
                self._observe_point(point, tick, attachment_id, index)
            self._point_count += len(points)
        if not rows:
            raise CaptureFramingEnvelopeError("Framing sample is empty")
        self._ticks.add(tick)
        self._sample_count += 1
        self._attachment_count += len(rows)
        if self._sample_count > MAX_SAMPLES \
                or self._attachment_count > MAX_ATTACHMENT_SAMPLES \
                or self._point_count > MAX_POINTS:
            raise CaptureFramingEnvelopeError("Framing evidence is excessive")
        _feed(self._digest, {"tick": tick, "attachments": rows})

    def finish(self) -> dict[str, Any]:
        if self._sample_count < 1 or set(self._extrema) != {
            "left", "right", "top", "bottom",
        }:
            raise CaptureFramingEnvelopeError("Framing evidence is incomplete")
        bounds = envelope_value([
            [self._extrema["left"][1], self._extrema["top"][1]],
            [self._extrema["right"][1], self._extrema["bottom"][1]],
        ])
        return {
            "sample_count": self._sample_count,
            "attachment_sample_count": self._attachment_count,
            "point_count": self._point_count,
            "evidence_sha256": self._digest.hexdigest(),
            "bounds_canvas": bounds,
            "bounds_runtime": canvas_bounds_to_runtime(
                bounds, self.canvas_height,
            ),
            "extrema_witnesses": {
                side: _witness(row) for side, row in self._extrema.items()
            },
        }

    def _observe_point(self, point, tick, attachment_id, index):
        x, y = point
        candidates = {
            "left": (x, x, tick, attachment_id, index, point),
            "right": (-x, x, tick, attachment_id, index, point),
            "top": (y, y, tick, attachment_id, index, point),
            "bottom": (-y, y, tick, attachment_id, index, point),
        }
        for side, candidate in candidates.items():
            if side not in self._extrema \
                    or candidate[:5] < self._extrema[side][:5]:
                self._extrema[side] = candidate


def setup_capture_envelope(context) -> dict[str, Any]:
    accumulator = CaptureEnvelopeAccumulator(
        "setup", context.canvas_size[1],
    )
    accumulator.observe(0, (
        (item.attachment_id, item.setup_vertices_xy)
        for item in context.attachments
    ))
    return accumulator.finish()


def observe_geometry(accumulator, tick, geometry) -> None:
    accumulator.observe(tick, (
        (item.attachment_id, item.posed_vertices_xy)
        for item in geometry.attachments
    ))


def build_capture_framing_envelope_set(
    setup, base, combined, canvas_height,
) -> CaptureFramingEnvelopeSet:
    envelopes = {"setup": setup, "base": base, "combined": combined}
    union_canvas, witnesses = union_canvas_envelope(envelopes)
    document = {
        "canvas_height": _q(canvas_height),
        "envelopes": envelopes,
        "union_envelope_canvas": union_canvas,
        "union_envelope_runtime": canvas_bounds_to_runtime(
            union_canvas, canvas_height,
        ),
        "union_extrema_witnesses": witnesses,
    }
    return CaptureFramingEnvelopeSet(_canonical(document))


def union_canvas_envelope(envelopes):
    minimum = [
        min(envelopes[kind]["bounds_canvas"]["min_xy"][axis]
            for kind in ENVELOPE_KINDS)
        for axis in (0, 1)
    ]
    maximum = [
        max(envelopes[kind]["bounds_canvas"]["max_xy"][axis]
            for kind in ENVELOPE_KINDS)
        for axis in (0, 1)
    ]
    bounds = envelope_value([minimum, maximum])
    witnesses = {}
    for side, axis, field in (
        ("left", 0, "min_xy"), ("right", 0, "max_xy"),
        ("top", 1, "min_xy"), ("bottom", 1, "max_xy"),
    ):
        target = bounds[field][axis]
        for kind in ENVELOPE_KINDS:
            witness = envelopes[kind]["extrema_witnesses"][side]
            if witness["point_xy"][axis] == target:
                witnesses[side] = {"envelope_kind": kind, **witness}
                break
    return bounds, witnesses


def canvas_bounds_to_runtime(bounds, canvas_height):
    minimum, maximum = bounds["min_xy"], bounds["max_xy"]
    return envelope_value([
        [_q(minimum[0]), _q(canvas_height - maximum[1])],
        [_q(maximum[0]), _q(canvas_height - minimum[1])],
    ])


def proposed_runtime_world_viewport(bounds, capture_viewport=CAPTURE_VIEWPORT):
    pixel_width = float(capture_viewport["width"])
    pixel_height = float(capture_viewport["height"])
    margin = capture_viewport["margin_px"]
    inner_width = pixel_width - margin["left"] - margin["right"]
    inner_height = pixel_height - margin["top"] - margin["bottom"]
    if inner_width <= 0 or inner_height <= 0:
        raise CaptureFramingEnvelopeError("Capture margin leaves no viewport")
    aspect = pixel_width / pixel_height
    required_width = bounds["size"][0] * pixel_width / inner_width
    required_height = bounds["size"][1] * pixel_height / inner_height
    world_width = max(required_width, required_height * aspect)
    world_height = world_width / aspect
    center_x, center_y = bounds["center_xy"]
    return {
        "x": _q(center_x - world_width / 2.0),
        "y": _q(center_y - world_height / 2.0),
        "width": _q(world_width), "height": _q(world_height),
    }


def contains_with_capture_margin(viewport, bounds, capture_viewport):
    pixel_width = float(capture_viewport["width"])
    pixel_height = float(capture_viewport["height"])
    margin = capture_viewport["margin_px"]
    left = viewport["x"] + viewport["width"] * margin["left"] / pixel_width
    right = viewport["x"] + viewport["width"] * (
        1.0 - margin["right"] / pixel_width
    )
    bottom = viewport["y"] + viewport["height"] * margin["bottom"] / pixel_height
    top = viewport["y"] + viewport["height"] * (
        1.0 - margin["top"] / pixel_height
    )
    tolerance = 1e-6
    return bounds["min_xy"][0] >= left - tolerance \
        and bounds["max_xy"][0] <= right + tolerance \
        and bounds["min_xy"][1] >= bottom - tolerance \
        and bounds["max_xy"][1] <= top + tolerance


def _witness(row):
    _sort_value, _edge_value, tick, attachment_id, index, point = row
    return {
        "tick": tick, "attachment_id": attachment_id,
        "vertex_index": index, "point_xy": list(point),
    }


def _point(value):
    return [_q(value[0]), _q(value[1])]


def _q(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(float(value)):
        raise CaptureFramingEnvelopeError("Capture framing number is invalid")
    result = round(float(value), NUMERIC_PRECISION_DECIMALS)
    return 0.0 if result == 0 else result


def _feed(digest, value):
    payload = _canonical(value).encode("utf-8")
    digest.update(len(payload).to_bytes(8, "big"))
    digest.update(payload)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))
