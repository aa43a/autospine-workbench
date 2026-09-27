"""Keep healthy setup-area regions while preserving parent compression."""
from .raw_compression_preservation import floors as parent_floors
from ..spine43.continuous_pose import area


def floors(parent, triangles, projected_areas, setup_areas):
    result = parent_floors(parent, triangles, projected_areas, setup_areas)
    protected = []
    for i,(tri,setup,projected) in enumerate(zip(triangles,setup_areas,projected_areas)):
        parent_ratio = area(parent,tri)/setup
        if .5 <= parent_ratio <= 2:
            # Solver headroom only; independent setup acceptance stays at .5.
            # Never demand extra area from an already valid, fixed parent surface.
            required = min(.505,parent_ratio)*setup/projected
            if required > 2:raise ValueError('parent_setup_floor_conflicts_with_projected_ceiling')
            result[i] = max(result[i], required)
            protected.append(i)
    return result, protected
