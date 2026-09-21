"""Conservative necessary area bounds for fixed vertices and displacement disks."""
import math
from ..spine43.continuous_pose import area


def inspect(points, triangles, reference_areas, free, budget, *, lower=.5, upper=2.):
    if (len(points) != len(free) or len(triangles) != len(reference_areas)
            or not math.isfinite(budget) or budget < 0 or not 0 < lower <= upper):
        raise ValueError('area_budget_input')
    if any(len(p) != 2 or not all(math.isfinite(v) for v in p) for p in points):
        raise ValueError('area_budget_nonfinite')
    witnesses = []
    for index, (tri, reference) in enumerate(zip(triangles, reference_areas)):
        if (len(tri) != 3 or len(set(tri)) != 3
                or any(type(i) is not int or not 0 <= i < len(points) for i in tri)
                or not math.isfinite(reference) or abs(reference) < 1e-12):
            raise ValueError('area_budget_triangle')
        a, b, c = [points[i] for i in tri]
        gradients = [((b[1]-c[1])/2, (c[0]-b[0])/2),
                     ((c[1]-a[1])/2, (a[0]-c[0])/2),
                     ((a[1]-b[1])/2, (b[0]-a[0])/2)]
        radii = [budget if free[i] else 0. for i in tri]
        # Exact expansion: linear gradients plus three cross products of
        # displacements. Triangle inequality gives an outer (not attainable) bound.
        change = sum(r*math.hypot(*g) for r,g in zip(radii,gradients))
        change += .5*sum(radii[i]*radii[(i+1)%3] for i in range(3))
        center = area(points,tri)/reference
        radius = change/abs(reference)
        lo, hi = center-radius, center+radius
        if hi < lower-1e-9 or lo > upper+1e-9:
            witnesses.append(dict(triangle=index, vertices=list(tri), free_vertices=sum(r>0 for r in radii),
                current_ratio=center, possible_ratio_outer_bounds=[lo,hi]))
    return dict(profile='triangle-displacement-disk-area-bound-v1', authority='none',
        status='infeasible_with_budget' if witnesses else 'no_individual_triangle_counterexample',
        budget_px=budget, limits=[lower,upper], tested_triangles=len(triangles), witnesses=witnesses,
        scope='necessary_individual_area_bounds_not_global_feasibility_or_solver_convergence')
