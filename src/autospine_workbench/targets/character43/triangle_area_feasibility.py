"""Conservative signed-area bounds under fixed vertices and displacement disks."""
import math
from ..spine43.continuous_pose import area


def inspect(points, triangles, setup_areas, free, budget, minimum_ratio=.5):
    if (len(points)!=len(free) or len(triangles)!=len(setup_areas)
            or not math.isfinite(budget) or budget<0
            or not math.isfinite(minimum_ratio) or minimum_ratio<=0
            or any(len(p)!=2 or any(not math.isfinite(x) for x in p) for p in points)
            or any(type(v) is not bool for v in free)):
        raise ValueError('triangle_feasibility_invalid_context')
    rows=[]
    for index,(tri,reference) in enumerate(zip(triangles,setup_areas)):
        if (len(tri)!=3 or len(set(tri))!=3 or any(type(v) is not int or not 0<=v<len(points) for v in tri)
                or not math.isfinite(reference) or abs(reference)<1e-12):
            raise ValueError('triangle_feasibility_invalid_triangle')
        a,b,c=[points[v] for v in tri]
        radii=[budget if free[v] else 0. for v in tri]
        gradients=[math.dist(b,c)/2,math.dist(c,a)/2,math.dist(a,b)/2]
        # Expansion around the uncorrected pose: linear gradient terms plus
        # three pairwise cross products. With <=1 free vertex the bound is exact.
        remainder=sum(r*g for r,g in zip(radii,gradients))
        remainder+=sum(radii[i]*radii[(i+1)%3] for i in range(3))/2
        original=area(points,tri)/reference
        upper=original+remainder/abs(reference)
        margin=minimum_ratio-upper
        rows.append(dict(triangle=index,free_vertices=sum(free[v] for v in tri),
            current_ratio=original,maximum_ratio_bound=upper,
            bound_exact=sum(r>0 for r in radii)<=1,
            impossible=margin>1e-10,deficit_ratio=max(0.,margin)))
    return dict(profile='triangle-displacement-area-bound-v1',authority='none',
        minimum_ratio=minimum_ratio,budget_px=budget,rows=rows,
        impossible_triangles=[r['triangle'] for r in rows if r['impossible']],
        scope='necessary_condition_only_not_mesh_feasibility_or_motion_acceptance')
