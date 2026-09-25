"""Conservative mesh-path distance certificates for fixed points and alpha ellipses."""
from copy import deepcopy
import math
import numpy as np
from .boundary_path_feasibility import inspect as path_bounds


def inspect(setup,triangles,fixed,free,regions):
    centers=deepcopy(fixed);radii={};movable=set(free)
    for row in regions:
        vertex=row['vertex'];inverse=np.asarray(row['inverse'],dtype=float)
        if (vertex not in movable or vertex in radii or inverse.shape!=(2,2)
                or not np.isfinite(inverse).all() or abs(np.linalg.det(inverse))<1e-10
                or not math.isfinite(row['radius']) or row['radius']<=0):
            raise ValueError('region_path_context_invalid')
        # A containing disk makes the lower distance bound conservative even
        # for rotated, sheared or strongly elongated material regions.
        radii[vertex]=float(np.linalg.norm(np.linalg.inv(inverse),ord=2))*row['radius']
        centers[vertex]=list(row['center'])
    paths=path_bounds(setup,triangles,centers,sorted(movable-radii.keys()))
    witnesses=[]
    for row in paths['witnesses']:
        a,b=row['vertices'];lower=max(0.,row['distance_px']-radii.get(a,0)-radii.get(b,0))
        if lower>row['maximum_distance_px']+1e-8:
            witnesses.append(dict(row,minimum_possible_distance_px=lower,
                endpoint_outer_radii_px=[radii.get(a,0),radii.get(b,0)],
                minimum_ratio=lower/row['maximum_distance_px']))
    return dict(status='contact_region_path_conflict' if witnesses else 'no_region_path_counterexample',
                witnesses=witnesses,max_edge_stretch=2.,authority='none',
                scope='necessary_conservative_distance_bound_not_full_feasibility')
