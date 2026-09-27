"""Necessary per-triangle bounds for fixed-origin disk displacement budgets."""
import math
from ..spine43.continuous_pose import area


def inspect(context, points, floors):
    triangles=context['row']['triangles'];refs=context['areas'];budget=context['budget']
    if len(floors)!=len(triangles) or len(refs)!=len(triangles) or not math.isfinite(budget) or budget<0:
        raise ValueError('area_budget_context_invalid')
    if len(context['free'])!=len(points) or any(len(p)!=2 or not all(math.isfinite(v) for v in p) for p in points):
        raise ValueError('area_budget_points_invalid')
    failures=[]
    for index,(tri,ref,floor) in enumerate(zip(triangles,refs,floors)):
        if not math.isfinite(ref) or abs(ref)<1e-12 or not math.isfinite(floor):
            raise ValueError('area_budget_reference_invalid')
        a,b,c=[points[v] for v in tri]
        gradients=[((b[1]-c[1])/2,(c[0]-b[0])/2),
                   ((c[1]-a[1])/2,(a[0]-c[0])/2),
                   ((a[1]-b[1])/2,(b[0]-a[0])/2)]
        radii=[budget if context['free'][v] else 0. for v in tri]
        # Linear terms plus the three cyclic displacement cross-products.
        # For <=1 movable vertex this is the exact maximum over its disk.
        bound=sum(r*math.hypot(*g) for r,g in zip(radii,gradients))
        bound+=.5*sum(radii[i]*radii[(i+1)%3] for i in range(3))
        maximum=area(points,tri)*(1 if ref>0 else -1)+bound
        required=floor*abs(ref)
        if maximum < required-1e-7:
            failures.append(dict(triangle=index,free_vertices=sum(context['free'][v] for v in tri),
                maximum_oriented_area=maximum,required_oriented_area=required,
                exact_disk_bound=sum(r>0 for r in radii)<=1))
    return dict(profile='triangle-displacement-disk-necessary-bound-v1',failures=failures,
                scope='counterexamples_only_not_joint_feasibility_proof')
