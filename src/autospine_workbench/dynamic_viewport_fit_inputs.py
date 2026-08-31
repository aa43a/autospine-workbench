"""Bounded normalization for DynamicViewportFit v1 evidence and framing."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import math
import re

from .resolved_project import canonical_sha256


NUMERIC_PRECISION_DECIMALS = 12
MAX_COORD_ABS = 1_000_000_000.0
MAX_VIEWPORT_DIMENSION = 1_000_000.0
MAX_SAMPLE_COUNT = 65_536
MAX_GEOMETRY_ITEM_COUNT = 262_144
MAX_POINT_COUNT = 2_000_000
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class DynamicViewportFitInputError(ValueError):
    """Raised when viewport-fit input is malformed, unbounded, or non-finite."""


def normalize_dynamic_viewport_inputs(sampled, bounds, viewport, margin):
    """Return canonical source metadata, envelope, viewport, and margins."""

    source, envelope = _normalize_source(sampled, bounds)
    normalized_viewport = viewport_value(viewport)
    normalized_margin = margin_value(margin, normalized_viewport)
    return source, envelope, normalized_viewport, normalized_margin


def viewport_value(value):
    row = mapping_value(value, "output viewport")
    if set(row) != {"width", "height"}:
        raise DynamicViewportFitInputError("Output viewport fields are unsupported")
    result = {field: number_value(row[field], field) for field in ("width", "height")}
    if any(not 1.0 <= item <= MAX_VIEWPORT_DIMENSION for item in result.values()):
        raise DynamicViewportFitInputError("Output viewport dimensions are invalid")
    return result


def margin_value(value, viewport):
    if isinstance(value, bool):
        raise DynamicViewportFitInputError("Viewport margin is invalid")
    if isinstance(value, (int, float)):
        number = number_value(value, "margin")
        result = dict.fromkeys(("left", "right", "top", "bottom"), number)
    else:
        row = mapping_value(value, "viewport margin")
        fields = {"left", "right", "top", "bottom"}
        if set(row) != fields:
            raise DynamicViewportFitInputError("Viewport margin fields are unsupported")
        result = {field: number_value(row[field], f"margin {field}") for field in fields}
    if any(item < 0.0 for item in result.values()) \
            or viewport["width"] - result["left"] - result["right"] < 1.0 \
            or viewport["height"] - result["top"] - result["bottom"] < 1.0:
        raise DynamicViewportFitInputError("Viewport margin leaves no bounded inner viewport")
    return {field: result[field] for field in ("left", "right", "top", "bottom")}


def envelope_value(extrema):
    minimum, maximum = extrema
    width, height = quantize(maximum[0] - minimum[0]), \
        quantize(maximum[1] - minimum[1])
    return {"min_xy": list(minimum), "max_xy": list(maximum),
            "size": [width, height],
            "center_xy": [quantize(minimum[0] + width / 2.0),
                          quantize(minimum[1] + height / 2.0)]}


def quantize(value):
    if not math.isfinite(value):
        raise DynamicViewportFitInputError("Dynamic viewport arithmetic is non-finite")
    result = round(float(value), NUMERIC_PRECISION_DECIMALS)
    return 0.0 if result == 0 else result


def number_value(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) or abs(float(value)) > MAX_COORD_ABS:
        raise DynamicViewportFitInputError(f"{label} must be a bounded finite number")
    return quantize(float(value))


def point_value(value):
    row = sequence_value(value, "point", 2, 2)
    return [number_value(row[0], "point x"), number_value(row[1], "point y")]


def mapping_value(value, label):
    if not isinstance(value, Mapping):
        raise DynamicViewportFitInputError(f"{label} must be an object")
    return value


def _normalize_source(sampled, bounds):
    if (sampled is None) == (bounds is None):
        raise DynamicViewportFitInputError(
            "Provide exactly one geometry source: sampled_geometry or point_bounds"
        )
    if sampled is not None:
        normalized, sample_count, item_count, point_count = _samples(sampled)
        kind = "sampled_attachment_geometry"
    else:
        normalized, item_count = _bounds(bounds)
        kind, sample_count, point_count = "point_bounds", 0, 0
    source = {
        "kind": kind, "evidence_sha256": canonical_sha256(normalized),
        "sample_count": sample_count, "geometry_item_count": item_count,
        "point_count": point_count,
    }
    return source, envelope_value(_source_extrema(normalized))


def _samples(value):
    rows = sequence_value(value, "sampled geometry", 1, MAX_SAMPLE_COUNT)
    result, ticks, item_count, point_count = [], set(), 0, 0
    for raw in rows:
        sample = mapping_value(raw, "sampled geometry row")
        tick = sample.get("tick")
        if type(tick) is not int or tick < 0 or tick in ticks:
            raise DynamicViewportFitInputError(
                "Sample ticks must be unique non-negative integers"
            )
        ticks.add(tick)
        attachments, ids = [], set()
        for raw_attachment in sequence_value(
            sample.get("attachments"), "sample attachments", 1,
            MAX_GEOMETRY_ITEM_COUNT,
        ):
            attachment = mapping_value(raw_attachment, "sample attachment")
            identifier = attachment.get("attachment_id")
            if not isinstance(identifier, str) or not _ID.fullmatch(identifier) \
                    or identifier in ids:
                raise DynamicViewportFitInputError("Sample attachment ids are invalid")
            ids.add(identifier)
            points = [point_value(row) for row in sequence_value(
                attachment.get("posed_vertices_xy"), "posed vertices", 1,
                MAX_POINT_COUNT,
            )]
            point_count += len(points)
            item_count += 1
            if point_count > MAX_POINT_COUNT or item_count > MAX_GEOMETRY_ITEM_COUNT:
                raise DynamicViewportFitInputError("Sampled geometry exceeds resource limits")
            attachments.append({"attachment_id": identifier,
                                "posed_vertices_xy": points})
        result.append({"tick": tick, "attachments": sorted(
            attachments, key=lambda row: row["attachment_id"]
        )})
    normalized = {"kind": "sampled_attachment_geometry",
                  "samples": sorted(result, key=lambda row: row["tick"])}
    return normalized, len(result), item_count, point_count


def _bounds(value):
    rows = [value] if isinstance(value, Mapping) else sequence_value(
        value, "point bounds", 1, MAX_GEOMETRY_ITEM_COUNT,
    )
    result = []
    for raw in rows:
        row = mapping_value(raw, "point bounds row")
        if set(row) != {"min_xy", "max_xy"}:
            raise DynamicViewportFitInputError("Point bounds fields are unsupported")
        minimum, maximum = point_value(row["min_xy"]), point_value(row["max_xy"])
        if minimum[0] > maximum[0] or minimum[1] > maximum[1]:
            raise DynamicViewportFitInputError("Point bounds minimum exceeds maximum")
        result.append({"min_xy": minimum, "max_xy": maximum})
    result.sort(key=lambda row: (*row["min_xy"], *row["max_xy"]))
    if len({canonical(row) for row in result}) != len(result):
        raise DynamicViewportFitInputError("Point bounds must be unique")
    return {"kind": "point_bounds", "bounds": result}, len(result)


def _source_extrema(source):
    if source["kind"] == "point_bounds":
        points = [point for row in source["bounds"]
                  for point in (row["min_xy"], row["max_xy"])]
    else:
        points = [point for sample in source["samples"]
                  for row in sample["attachments"]
                  for point in row["posed_vertices_xy"]]
    return [[min(point[0] for point in points), min(point[1] for point in points)],
            [max(point[0] for point in points), max(point[1] for point in points)]]


def sequence_value(value, label, minimum, maximum):
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) \
            or not minimum <= len(value) <= maximum:
        raise DynamicViewportFitInputError(f"{label} has invalid cardinality")
    return list(value)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))
