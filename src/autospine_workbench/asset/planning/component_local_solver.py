"""Bounded per-pose area projection; fixed vertices and bind data stay untouched."""
import math
from ..joints.mesh_weights import _area

ITERATIONS = 48


def metrics(setup, points, triangles):
    ratios = [_area(points,t)/_area(setup,t) for t in triangles]
    edges = sorted({tuple(sorted((a,b))) for t in triangles for a,b in zip(t,t[1:]+t[:1])})
    stretches = [math.dist(points[a],points[b])/math.dist(setup[a],setup[b]) for a,b in edges]
    bad = [i for i,r in enumerate(ratios) if r < .5 or r > 2]
    return dict(inversions=sum(r<=0 for r in ratios), min_area_ratio=min(ratios),
                max_area_ratio=max(ratios), max_edge_stretch=max(stretches), bad_triangles=bad)


def solve(mesh, points, joint_index, budget):
    if not math.isfinite(budget) or budget <= 0:
        raise ValueError('component_correction_budget_invalid')
    setup, triangles = mesh['vertices_xy'], mesh['triangles']
    if len(points) != len(setup) or any(not math.isfinite(v) for p in points for v in p):
        raise ValueError('component_correction_points_invalid')
    before = metrics(setup,points,triangles)
    bad_vertices = {v for i in before['bad_triangles'] for v in triangles[i]}
    # One triangle ring around observed defects, restricted to mixed joint weights.
    ring = {v for t in triangles if any(v in bad_vertices for v in t) for v in t}
    free = [i in ring and 0 < sum(w['weight'] for w in row[joint_index:]) < 1
            for i,row in enumerate(mesh['weights'])]
    moved = [p[:] for p in points]
    areas = [_area(setup,t) for t in triangles]
    edges = sorted({tuple(sorted((a,b))) for t in triangles for a,b in zip(t,t[1:]+t[:1])})
    for _ in range(ITERATIONS):
        for t, area in zip(triangles,areas):
            ratio = _area(moved,t)/area
            target = max(.55,min(1.9,ratio))
            if target == ratio: continue
            a,b,c = [moved[i] for i in t]
            gradients = [[(b[1]-c[1])/2,(c[0]-b[0])/2],[(c[1]-a[1])/2,(a[0]-c[0])/2],[(a[1]-b[1])/2,(b[0]-a[0])/2]]
            divisor = sum(sum(v*v for v in g) for i,g in zip(t,gradients) if free[i])
            if divisor < 1e-18: continue
            scale = (target-ratio)*area/divisor
            for i,g in zip(t,gradients):
                if free[i]:
                    for k in (0,1): moved[i][k] += scale*g[k]
        for a,b in edges:
            length = math.dist(setup[a],setup[b]); distance = math.dist(moved[a],moved[b])
            count = int(free[a])+int(free[b])
            if count and distance > 1.9*length:
                delta = [(moved[b][k]-moved[a][k])*(distance-1.9*length)/distance/count for k in (0,1)]
                for k in (0,1):
                    if free[a]: moved[a][k] += delta[k]
                    if free[b]: moved[b][k] -= delta[k]
        for i in range(len(moved)):
            distance = math.dist(moved[i],points[i])
            if free[i] and distance > budget:
                moved[i] = [points[i][k]+(moved[i][k]-points[i][k])*budget/distance for k in (0,1)]
    if any(not math.isfinite(v) for p in moved for v in p):
        raise ValueError('component_correction_nonfinite')
    after = metrics(setup,moved,triangles)
    improves = (after['inversions'] < before['inversions'] or len(after['bad_triangles']) < len(before['bad_triangles']))
    admissible = (improves and after['inversions'] <= before['inversions']
                  and set(after['bad_triangles']) <= set(before['bad_triangles'])
                  and after['max_edge_stretch'] <= max(2.,before['max_edge_stretch']))
    return dict(points=moved if admissible else [p[:] for p in points], trial_qa=after,
                before_qa=before, selected_qa=after if admissible else before,
                selected=admissible, free_vertices=[i for i,v in enumerate(free) if v],
                max_trial_offset=max(math.dist(a,b) for a,b in zip(points,moved)), budget_px=budget)
