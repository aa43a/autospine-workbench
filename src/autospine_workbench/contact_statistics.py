"""Stable summary statistics for overlap and bounded-gap contacts."""

from __future__ import annotations

from dataclasses import dataclass
import math


CanvasRun = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class ContactEvidence:
    id: str
    area: int
    bbox_xywh: tuple[int, int, int, int]
    centroid_xy: tuple[float, float]
    variance_xy: tuple[float, float]
    error_radius: float
    overlap_ratio_a: float
    overlap_ratio_b: float
    representative_xy: tuple[float, float]
    mode: str
    gap_distance_px: float
    source_xy_a: tuple[float, float]
    source_xy_b: tuple[float, float]

    def to_contract(
        self,
        *,
        contact_id: str,
        joint_id: str,
        relation: str,
        layer_ids: tuple[str, str],
        flags: tuple[str, ...],
    ) -> dict[str, object]:
        """Serialize this statistic into the alpha-evidence contact contract."""

        return {
            "contact_id": contact_id,
            "joint_id": joint_id,
            "relation": relation,
            "layer_ids": list(layer_ids),
            "mode": self.mode,
            "area": self.area,
            "bbox_xywh": list(self.bbox_xywh),
            "centroid_xy": list(self.centroid_xy),
            "variance_xy": list(self.variance_xy),
            "representative_xy": list(self.representative_xy),
            "error_radius_px": self.error_radius,
            "overlap_ratios": [self.overlap_ratio_a, self.overlap_ratio_b],
            "gap_distance_px": self.gap_distance_px,
            "endpoints_xy": [list(self.source_xy_a), list(self.source_xy_b)],
            "flags": list(flags),
        }


@dataclass(frozen=True, slots=True)
class ContactSite:
    relation: str
    joint_name: str
    layer_ids: tuple[str, str]
    evidence: ContactEvidence
    flags: tuple[str, ...] = ()


@dataclass(slots=True)
class ContactSections:
    contacts: list[dict[str, object]]
    joint_contact_ids: dict[str, list[str]]
    joint_flags: dict[str, list[str]]
    qa_flags: set[str]


def overlap_evidence(runs: tuple[CanvasRun, ...], area_a: int, area_b: int) -> ContactEvidence:
    area = sum(x1 - x0 + 1 for _, x0, x1 in runs)
    sum_x = sum((x0 + x1) * (x1 - x0 + 1) // 2 for _, x0, x1 in runs)
    sum_y = sum(y * (x1 - x0 + 1) for y, x0, x1 in runs)
    sum_x2 = sum(_square_prefix(x1) - _square_prefix(x0 - 1) for _, x0, x1 in runs)
    sum_y2 = sum(y * y * (x1 - x0 + 1) for y, x0, x1 in runs)
    cx, cy = sum_x / area, sum_y / area
    variance_x = max(0.0, sum_x2 / area - cx * cx)
    variance_y = max(0.0, sum_y2 / area - cy * cy)
    left, right = min(run[1] for run in runs), max(run[2] for run in runs)
    top, bottom = min(run[0] for run in runs), max(run[0] for run in runs)
    representative = _representative(runs, cx, cy)
    return ContactEvidence(
        "",
        area,
        (left, top, right - left + 1, bottom - top + 1),
        (_round6(cx), _round6(cy)),
        (_round6(variance_x), _round6(variance_y)),
        _round6(math.sqrt(variance_x + variance_y)),
        _round6(area / area_a),
        _round6(area / area_b),
        representative,
        "overlap",
        0.0,
        representative,
        representative,
    )


def gap_evidence(
    point_a: tuple[float, float], point_b: tuple[float, float], distance: float
) -> ContactEvidence:
    cx, cy = (point_a[0] + point_b[0]) / 2, (point_a[1] + point_b[1]) / 2
    variance_x = (point_a[0] - point_b[0]) ** 2 / 4
    variance_y = (point_a[1] - point_b[1]) ** 2 / 4
    left, top = int(min(point_a[0], point_b[0])), int(min(point_a[1], point_b[1]))
    right, bottom = int(max(point_a[0], point_b[0])), int(max(point_a[1], point_b[1]))
    return ContactEvidence(
        "gap.000",
        0,
        (left, top, right - left + 1, bottom - top + 1),
        (_round6(cx), _round6(cy)),
        (_round6(variance_x), _round6(variance_y)),
        _round6(distance / 2),
        0.0,
        0.0,
        (_round6(cx), _round6(cy)),
        "gap",
        distance,
        point_a,
        point_b,
    )


def round6(value: float) -> float:
    return _round6(value)


def _representative(runs: tuple[CanvasRun, ...], cx: float, cy: float) -> tuple[float, float]:
    best: tuple[float, int, int] | None = None
    for y, x0, x1 in runs:
        for target in (math.floor(cx), math.ceil(cx)):
            x = min(max(target, x0), x1)
            ranking = ((x - cx) ** 2 + (y - cy) ** 2, y, x)
            if best is None or ranking < best:
                best = ranking
    assert best is not None
    return (float(best[2]), float(best[1]))


def _square_prefix(value: int) -> int:
    """Polynomial prefix supports interval differences across negative x."""

    return value * (value + 1) * (2 * value + 1) // 6


def _round6(value: float) -> float:
    return round(float(value), 6)
