"""Explicit per-triangle floors for preserving healthy projected shape."""
import math
from ..spine43.continuous_pose import area


def minimum_ratios(context):
    values = context.get('minimum_ratios')
    if values is None:
        return [.5]*len(context['row']['triangles'])
    if (len(values) != len(context['row']['triangles']) or
            any(not math.isfinite(v) or not .5 <= v <= 1 for v in values)):
        raise ValueError('area_preservation_invalid_floors')
    return list(values)


def from_pose(points, triangles, references):
    if len(triangles) != len(references) or any(not math.isfinite(a) or abs(a)<1e-12 for a in references):
        raise ValueError('area_preservation_invalid_references')
    ratios = [area(points,t)/a for t,a in zip(triangles,references)]
    if any(not math.isfinite(r) for r in ratios):
        raise ValueError('area_preservation_nonfinite_pose')
    # Do not preserve a pre-existing expansion beyond the projected reference.
    return [max(.5,min(1.,r)) for r in ratios]


def outside_repair_band(points, triangles, references):
    """Preserve distant healthy shape; keep the existing floor in one repair ring."""
    floors = from_pose(points, triangles, references)
    seeds = {i for i,(t,a) in enumerate(zip(triangles,references)) if not .5<=area(points,t)/a<=2}
    vertices = {v for i in seeds for v in triangles[i]}
    band = [i for i,t in enumerate(triangles) if vertices.intersection(t)]
    for i in band:floors[i]=.5
    return floors, band
