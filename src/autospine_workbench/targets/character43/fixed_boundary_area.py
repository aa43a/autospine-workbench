"""Necessary area-sum bounds for variable patches enclosed by fixed vertices."""
from collections import Counter
import math
from ..spine43.continuous_pose import area


def inspect(context, points, floors):
    triangles=context['row']['triangles'];refs=context['areas'];free=context['free']
    if len(refs)!=len(triangles) or len(floors)!=len(triangles) or len(points)!=len(free):
        raise ValueError('fixed_boundary_area_inventory')
    if any(not math.isfinite(v) for p in points for v in p) or any(not math.isfinite(r) or abs(r)<1e-12 for r in refs):
        raise ValueError('fixed_boundary_area_nonfinite')
    if any(not math.isfinite(f) or f<0 for f in floors):raise ValueError('fixed_boundary_area_floor')
    incident={v:set() for v,enabled in enumerate(free) if enabled}
    for i,tri in enumerate(triangles):
        for v in tri:
            if free[v]:incident[v].add(i)
    remaining=set(incident);patches=[]
    while remaining:
        frontier={min(remaining)};vertices=set();selected=set()
        while frontier:
            vertices.update(frontier)
            attached=set().union(*(incident[v] for v in frontier));selected.update(attached)
            frontier={v for i in attached for v in triangles[i] if free[v]}-vertices
        remaining-=vertices
        oriented=Counter();valid=True
        for i in selected:
            tri=triangles[i] if refs[i]>0 else list(reversed(triangles[i]))
            for a,b in zip(tri,tri[1:]+tri[:1]):oriented[a,b]+=1
        boundary=[]
        for a,b in sorted({tuple(sorted(e)) for e in oriented}):
            forward=oriented[a,b];back=oriented[b,a]
            if forward+back>2 or (forward+back==2 and forward!=back):valid=False
            if forward!=back:boundary.append((a,b))
        closed=valid and bool(boundary) and all(not free[a] and not free[b] for a,b in boundary)
        if not closed:continue
        actual=sum(area(points,triangles[i])*(1 if refs[i]>0 else -1) for i in selected)
        minimum=sum(floors[i]*abs(refs[i]) for i in selected)
        # Aggregate the existing per-triangle final ratio tolerance, rather than
        # demanding exact equality from a floating-point tessellation.
        tolerance=1e-7*sum(abs(refs[i]) for i in selected)
        patches.append(dict(triangles=sorted(selected),movable_vertices=sorted(vertices),
            boundary_vertices=sorted({v for e in boundary for v in e}),
            fixed_area=actual,minimum_area=minimum,deficit=minimum-actual,
            tolerance=tolerance,infeasible=minimum>actual+tolerance))
    return dict(profile='fixed-boundary-area-sum-necessary-v1',patches=patches,
                infeasible_patches=sum(p['infeasible'] for p in patches),
                scope='necessary_bounds_not_complete_feasibility_or_visual_proof')
