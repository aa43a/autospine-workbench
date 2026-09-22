"""Opt-in floors against worsening pre-existing setup-relative compression."""
import math
from .area_preservation import from_pose
from ..spine43.continuous_pose import area

CONTRACT='raw-compression-preservation-v1-experiment'


def floors(points, triangles, projected_areas, setup_areas):
    if len(setup_areas)!=len(triangles) or any(not math.isfinite(a) or abs(a)<1e-12 for a in setup_areas):
        raise ValueError('raw_preservation_invalid_setup')
    result=from_pose(points,triangles,projected_areas)
    for i,(tri,setup,projected) in enumerate(zip(triangles,setup_areas,projected_areas)):
        value=area(points,tri)
        if setup*projected<=0:raise ValueError('raw_preservation_reference_orientation')
        if 0<value/setup<.5:
            result[i]=max(result[i],value/projected)
            if result[i]>2:raise ValueError('raw_preservation_conflicts_with_projected_ceiling')
    return result
