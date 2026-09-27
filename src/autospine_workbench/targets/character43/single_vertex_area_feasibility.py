"""Pairwise necessary disk bounds for area floors sharing one movable vertex."""
from itertools import combinations
import math
from ..spine43.continuous_pose import area


def inspect(context, points, floors):
    triangles=context['row']['triangles'];refs=context['areas'];free=context['free'];budget=context['budget']
    if len(refs)!=len(triangles) or len(floors)!=len(triangles) or len(free)!=len(points):
        raise ValueError('single_vertex_area_inventory')
    if not math.isfinite(budget) or budget<0 or any(not math.isfinite(v) for p in points for v in p):
        raise ValueError('single_vertex_area_nonfinite')
    constraints={}
    for i,(tri,ref,floor) in enumerate(zip(triangles,refs,floors)):
        if not math.isfinite(ref) or abs(ref)<1e-12 or not math.isfinite(floor):
            raise ValueError('single_vertex_area_reference')
        vertices=[v for v in tri if free[v]]
        if len(vertices)!=1:continue
        vertex=vertices[0];index=tri.index(vertex)
        a,b,c=[points[tri[(index+k)%3]] for k in range(3)]
        sign=1 if ref>0 else -1
        gradient=((b[1]-c[1])/2*sign,(c[0]-b[0])/2*sign)
        length=math.hypot(*gradient)
        if length<=1e-12:continue
        # Match independent final ratio checks; do not demand solver headroom.
        required=max(.5,floor-1e-7)*abs(ref)
        normal=tuple(v/length for v in gradient)
        lower=(required-area(points,tri)*sign)/length
        constraints.setdefault(vertex,[]).append((i,normal,lower))
    failures=[]
    for vertex,rows in constraints.items():
        for a,b in combinations(rows,2):
            required=a[2]+b[2]
            maximum=budget*math.hypot(a[1][0]+b[1][0],a[1][1]+b[1][1])
            if required>maximum+1e-7:
                failures.append(dict(vertex=vertex,triangles=[a[0],b[0]],
                    required_normal_displacement_sum=required,
                    maximum_normal_displacement_sum=maximum,deficit=required-maximum,
                    normals=[a[1],b[1]],budget_px=budget))
    return dict(profile='shared-single-vertex-area-disk-bound-v1',failures=failures,
                scope='necessary_pairwise_counterexamples_not_complete_feasibility')
