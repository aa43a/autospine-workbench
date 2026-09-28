"""Bounded iterative projection; v2 keeps the displacement origin fixed across sweeps."""
import math
from ..spine43.continuous_pose import area
from .interpolation_area_margin import targets


def project(context, base, *, initial=None):
    points = [list(p) for p in (base if initial is None else initial)]
    triangles, areas = context['row']['triangles'], context['areas']
    free, budget = context['free'], context['budget']
    edges, lengths = context['edges'], context['lengths']
    floors = targets(context)
    if not math.isfinite(budget) or budget < 0 or any(abs(a) < 1e-12 for a in areas):
        raise ValueError('character_area_projection_invalid_context')
    if any(not math.isfinite(v) for p in points for v in p):
        raise ValueError('character_area_projection_nonfinite')
    if len(points) != len(base) or any(len(p) != 2 for p in points):
        raise ValueError('character_area_projection_initial_shape')
    if initial is not None:
        for i, origin in enumerate(base):
            if not free[i]:
                points[i] = list(origin)
            else:
                distance = math.dist(points[i], origin)
                if distance > budget:
                    points[i] = [origin[k]+(points[i][k]-origin[k])*budget/distance for k in (0,1)]
    # A pose strictly inside every solver target is a fixed point: none of the
    # first 48 sweeps can change it. Preserve the historical convergence record
    # while avoiding those repeated no-op triangle/edge passes on long clips.
    ratios = [area(points, tri)/reference for tri, reference in zip(triangles, areas)]
    if (ratios and max(ratios) <= 1.91 and all(r == max(.55, floor, min(1.9, r)) for r, floor in zip(ratios, floors))
            and all(math.dist(points[a], points[b]) <= 1.9*length
                    for (a, b), length in zip(edges, lengths))):
        return points, dict(iterations=48, converged=True, lower_target=.55)
    converged = False
    # Fixed constraints still participate in every convergence check. They cannot
    # change points, so omit only their no-op update passes (not their evidence).
    active_triangles = [(tri, reference, floor) for tri, reference, floor in zip(triangles, areas, floors)
                        if any(free[i] for i in tri)]
    active_edges = [(a, b, length, int(free[a])+int(free[b]))
                    for (a, b), length in zip(edges, lengths) if free[a] or free[b]]
    free_origins = [(i, origin) for i, origin in enumerate(base) if free[i]]
    # These are solver margins, not the independent QA floor (which remains .5).
    # In a narrow fixed boundary, .55 can be infeasible while .5 remains feasible.
    for iteration in range(1536):
        lower_target = (.55, .525, .5125, .50625)[iteration//384]
        for tri, reference, floor in active_triangles:
            ratio = area(points, tri)/reference
            target = max(lower_target, floor, min(1.9, ratio))
            if ratio == target:
                continue
            a, b, c = [points[i] for i in tri]
            gradients = [[(b[1]-c[1])/2, (c[0]-b[0])/2],
                         [(c[1]-a[1])/2, (a[0]-c[0])/2],
                         [(a[1]-b[1])/2, (b[0]-a[0])/2]]
            denominator = sum(sum(v*v for v in g) for i, g in zip(tri, gradients) if free[i])
            if denominator <= 1e-18:
                continue
            scale = (target-ratio)*reference/denominator
            for i, gradient in zip(tri, gradients):
                if free[i]:
                    for axis in (0, 1):
                        points[i][axis] += scale*gradient[axis]
        for a, b, length, count in active_edges:
            delta = [points[b][i]-points[a][i] for i in (0, 1)]
            distance = math.hypot(*delta)
            if distance <= 1.9*length:
                continue
            scale = (distance-1.9*length)/distance/count
            for axis in (0, 1):
                if free[a]: points[a][axis] += scale*delta[axis]
                if free[b]: points[b][axis] -= scale*delta[axis]
        for i, origin in free_origins:
            distance = math.dist(points[i], origin)
            if distance > budget:
                points[i] = [origin[k]+(points[i][k]-origin[k])*budget/distance for k in (0, 1)]
        if (iteration+1) % 48 == 0:
            ratios = [area(points, t)/a for t, a in zip(triangles, areas)]
            converged = min(ratios) >= max(.5001, lower_target-.01) and max(ratios) <= 1.91 and all(
                math.dist(points[a], points[b]) <= 1.91*length
                for (a, b), length in zip(edges, lengths))
            if 'minimum_ratios' in context:
                converged = converged and all(r >= f-1e-7 for r,f in zip(ratios,floors))
            if converged:
                break
    if any(not math.isfinite(v) for p in points for v in p):
        raise ValueError('character_area_projection_nonfinite')
    return points, dict(iterations=iteration+1, converged=converged, lower_target=lower_target)
