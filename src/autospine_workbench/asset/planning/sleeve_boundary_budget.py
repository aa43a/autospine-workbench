"""Exact one-free-vertex area displacement bound; explicit bounded candidate policy."""
import math
from ..joints.mesh_weights import _area


def estimate(setup,triangles,points,free,base_budget,include_edges=False):
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
    edge_requirements=[];fixed_edges=[]
    if include_edges:
        edges=sorted({tuple(sorted((a,b))) for t in triangles for a,b in zip(t,t[1:]+t[:1])})
        for a,b in edges:
            excess=math.dist(points[a],points[b])-1.9*math.dist(setup[a],setup[b])
            if excess<=0:continue
            count=int(a in free)+int(b in free)
            if not count:fixed_edges.append([a,b]);continue
            # Triangle inequality: each free endpoint must have this much available budget.
            edge_requirements.append(dict(edge=[a,b],free_endpoints=count,required_px=excess/count))
        lower=max(lower,max((r['required_px'] for r in edge_requirements),default=0.))
    # base = 15% forearm; hard cap = 50% forearm. Geometry gates are unchanged.
    cap=base_budget*(.5/.15);budget=min(cap,max(base_budget,lower*1.1))
    evidence=dict(profile='area-edge-displacement-bound-cap50-v1' if include_edges else 'one-free-area-bound-cap50-v1',base_budget_px=base_budget,cap_px=cap,
        required_lower_bound_px=lower,budget_px=budget,cap_exceeded=lower>cap,
        fixed_triangle_failures=fixed_failures,requirements=requirements)
    if include_edges:evidence.update(edge_requirements=edge_requirements,fixed_edge_failures=fixed_edges)
    return budget,evidence
