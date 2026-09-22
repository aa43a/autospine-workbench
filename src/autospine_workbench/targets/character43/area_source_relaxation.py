"""Bounded recovery toward the same-frame source inside existing constraints."""
import math
from .interpolation_area_margin import targets
from ..spine43.continuous_pose import area


def relax(context, source, corrected, *, passes=4):
    if type(passes) is not int or not 1 <= passes <= 8:
        raise ValueError('area_relaxation_pass_limit')
    points=[list(p) for p in corrected]
    if len(points)!=len(source) or any(len(p)!=2 or not all(math.isfinite(v) for v in p)
                                     for p in [*points,*source]):
        raise ValueError('area_relaxation_points_invalid')
    triangles=context['row']['triangles'];refs=context['areas'];floors=targets(context)
    # Retain existing solver headroom where available; relaxation must not
    # deliberately pull a healthy boundary back to the QA threshold.
    floors=[max(f,min(.55,area(points,t)/r)) for f,t,r in zip(floors,triangles,refs)]
    edges=context['edges'];lengths=context['lengths'];budget=context['budget'];free=context['free']
    adjacent=[[] for _ in points];incident=[[] for _ in points]
    for i,tri in enumerate(triangles):
        for v in tri:adjacent[v].append(i)
    for i,edge in enumerate(edges):
        for v in edge:incident[v].append(i)
    def valid(v):
        if math.dist(points[v],source[v])>budget+1e-7:return False
        if not free[v] and math.dist(points[v],source[v])>1e-7:return False
        if any(not floors[i]-1e-7 <= area(points,triangles[i])/refs[i] <= 2 for i in adjacent[v]):return False
        return all(math.dist(points[edges[i][0]],points[edges[i][1]])<=2*lengths[i]+1e-7 for i in incident[v])
    report=dict(profile='feasible-source-relaxation-v1-experiment',authority='none',selected=False)
    if not all(valid(v) for v in range(len(points))):
        return points,dict(report,status='initial_constraints_failed',changed_vertices=0)
    initial=sum(math.dist(a,b)**2 for a,b in zip(points,source))
    completed=0
    for _ in range(passes):
        moved=False;completed+=1
        groups={tuple(v for v in tri if free[v]) for tri in triangles}
        groups.update((v,) for v in range(len(points)) if free[v])
        order=sorted(groups,key=lambda group:(-sum(math.dist(points[v],source[v])**2 for v in group),group))
        for group in order:
            if not group or max(math.dist(points[v],source[v]) for v in group)<1e-7:continue
            before={v:points[v] for v in group}
            for fraction in (1.,.5,.25,.125,.0625):
                for v in group:points[v]=[a+(b-a)*fraction for a,b in zip(before[v],source[v])]
                if all(valid(v) for v in group):moved=True;break
                for v in group:points[v]=before[v]
        if not moved:break
    return points,dict(report,status='candidate',passes=completed,
        changed_vertices=sum(math.dist(a,b)>1e-7 for a,b in zip(points,corrected)),
        squared_displacement_before=initial,
        squared_displacement_after=sum(math.dist(a,b)**2 for a,b in zip(points,source)),
        scope='single_frame_feasibility_not_temporal_or_visual_acceptance')
