"""Exact one-free-vertex area displacement bound; explicit bounded candidate policy."""
import math
from ..joints.mesh_weights import _area


def estimate(setup,triangles,points,free,base_budget):
    if not math.isfinite(base_budget) or base_budget<=0:raise ValueError('boundary_budget_invalid')
    free=set(free);requirements=[];fixed_failures=[]
    for index,t in enumerate(triangles):
        rest=_area(setup,t)
        if abs(rest)<1e-9:raise ValueError('boundary_budget_degenerate')
        ratio=_area(points,t)/rest;target=max(.55,min(1.9,ratio))
        if ratio==target:continue
        moving=[i for i in t if i in free]
        if not moving:fixed_failures.append(index);continue
        if len(moving)!=1:continue
        k=t.index(moving[0]);a=points[t[(k+1)%3]];b=points[t[(k+2)%3]]
        gradient=math.dist(a,b)/(2*abs(rest))
        if gradient<=1e-12:fixed_failures.append(index);continue
        required=abs(target-ratio)/gradient
        requirements.append(dict(triangle=index,vertex=moving[0],required_px=required))
    lower=max((r['required_px'] for r in requirements),default=0.)
    # base = 15% forearm; hard cap = 50% forearm. Geometry gates are unchanged.
    cap=base_budget*(.5/.15);budget=min(cap,max(base_budget,lower*1.1))
    return budget,dict(profile='one-free-area-bound-cap50-v1',base_budget_px=base_budget,cap_px=cap,
        required_lower_bound_px=lower,budget_px=budget,cap_exceeded=lower>cap,
        fixed_triangle_failures=fixed_failures,requirements=requirements)
