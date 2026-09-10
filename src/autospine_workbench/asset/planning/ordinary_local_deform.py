"""Local pose-only cuff/sleeve projection with exact protected vertex domains."""
import math
from .component_local_solver import metrics
from .component_temporal_qa import passed
from ..joints.mesh_weights import _area

PROFILE = 'ordinary-local-role-projection48-v1'
ITERATIONS = 48


def solve(mesh, points, assignments, budget):
    """Return selected points and rejected-trial evidence; no binding is modified."""
    if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not math.isfinite(budget) or budget <= 0:
        raise ValueError('ordinary_deform_budget_invalid')
    setup, triangles = mesh['vertices_xy'], mesh['triangles']
    count = len(setup)
    if (not count or not triangles or len(points) != count
            or any(len(p) != 2 or any(isinstance(v, bool) or not isinstance(v, (int, float))
                or not math.isfinite(v) for v in p) for p in list(points)+list(setup))):
        raise ValueError('ordinary_deform_points_invalid')
    if len(assignments) != len(triangles):
        raise ValueError('ordinary_deform_assignment_inventory')
    roles = [set() for _ in setup]; adjacent = [set() for _ in setup]
    for index, (triangle, item) in enumerate(zip(triangles, assignments)):
        if (len(triangle) != 3 or len(set(triangle)) != 3
                or any(type(i) is not int or not 0 <= i < count for i in triangle)):
            raise ValueError('ordinary_deform_triangle_invalid')
        if (item.get('triangle_id', index) != index
                or item.get('role') not in {'hand','unknown','sleeve','cuff','hanging_cloth'}):
            raise ValueError('ordinary_deform_assignment_invalid')
        for i in triangle:
            roles[i].add(item['role']); adjacent[i].add(index)
    areas = [_area(setup, t) for t in triangles]
    if any(not math.isfinite(a) or abs(a) < 1e-12 for a in areas):
        raise ValueError('ordinary_deform_degenerate_setup')
    edges = sorted({tuple(sorted((a,b))) for t in triangles for a,b in zip(t,t[1:]+t[:1])})
    lengths = {edge:math.dist(setup[edge[0]],setup[edge[1]]) for edge in edges}
    before = metrics(setup, points, triangles)
    bad = set(before['bad_triangles'])
    seed = {v for i in bad for v in triangles[i]}
    # Include edge-only defects; they need not have an invalid triangle area.
    for a,b in edges:
        if math.dist(points[a],points[b]) > 2.*lengths[(a,b)]: seed.update((a,b))
    ring_triangles = {t for i in seed for t in adjacent[i]}
    ring = {v for t in ring_triangles for v in triangles[t]}
    free = {i for i in ring if roles[i] and roles[i] <= {'sleeve','cuff'}}
    active = sorted({t for i in free for t in adjacent[i]})
    moving_edges = [(a,b,lengths[(a,b)]) for a,b in edges if a in free or b in free]
    moved = [list(p) for p in points]
    free_order = sorted(free)
    for _ in range(ITERATIONS):
        for index in active:
            t,area = triangles[index],areas[index]
            ratio = _area(moved,t)/area
            target = max(.55,min(1.9,ratio))
            if target == ratio: continue
            a,b,c = [moved[i] for i in t]
            gradients = [[(b[1]-c[1])/2,(c[0]-b[0])/2],[(c[1]-a[1])/2,(a[0]-c[0])/2],[(a[1]-b[1])/2,(b[0]-a[0])/2]]
            divisor = sum(sum(v*v for v in g) for i,g in zip(t,gradients) if i in free)
            if divisor < 1e-18: continue
            scale = (target-ratio)*area/divisor
            for i,g in zip(t,gradients):
                if i in free:
                    for k in (0,1): moved[i][k] += scale*g[k]
        for a,b,length in moving_edges:
            distance = math.dist(moved[a],moved[b])
            if distance <= 1.9*length: continue
            n = int(a in free)+int(b in free)
            delta = [(moved[b][k]-moved[a][k])*(distance-1.9*length)/distance/n for k in (0,1)]
            for k in (0,1):
                if a in free: moved[a][k] += delta[k]
                if b in free: moved[b][k] -= delta[k]
        for i in free_order:
            distance = math.dist(moved[i],points[i])
            if distance > budget:
                moved[i] = [points[i][k]+(moved[i][k]-points[i][k])*budget/distance for k in (0,1)]
    if any(not math.isfinite(v) for p in moved for v in p):
        raise ValueError('ordinary_deform_nonfinite')
    after = metrics(setup,moved,triangles)
    reasons = []
    if after['inversions'] > before['inversions']: reasons.append('new_inversion')
    if not set(after['bad_triangles']) <= set(before['bad_triangles']): reasons.append('new_area_failure')
    if after['max_edge_stretch'] > max(2.,before['max_edge_stretch'])+1e-9: reasons.append('edge_stretch_regression')
    if passed(before) and not passed(after): reasons.append('new_failed_pose')
    gain = (after['inversions'] < before['inversions']
            or len(after['bad_triangles']) < len(before['bad_triangles'])
            or not passed(before) and passed(after))
    if not gain: reasons.append('no_sampled_gain')
    selected = not reasons
    return dict(profile=PROFILE, points=moved if selected else [list(p) for p in points],
        before_qa=before, trial_qa=after, selected_qa=after if selected else before,
        selected=selected, reason_codes=reasons or ['sampled_improvement'],
        free_vertices=free_order, protected_vertices=[i for i in range(count) if i not in free],
        max_trial_offset=max(math.dist(a,b) for a,b in zip(points,moved)), budget_px=budget,
        iterations=ITERATIONS, authority='none', production_authorized=False)
