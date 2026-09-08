"""Bounded residual corrections around an immutable existing deform."""
import math
from .alpha_seam import position
from .continuous_pose import area
from .seam_shape_solver import solve as proposal


def geometry(reference,points,triangles):
    if any(not math.isfinite(v) for p in points for v in p):return False
    for tri in triangles:
        base=area(reference,tri)
        if abs(base)<1e-12:raise ValueError('increment_degenerate_reference')
        if not .5<=area(points,tri)/base<=2.:return False
    edges={tuple(sorted((t[i],t[(i+1)%3]))) for t in triangles for i in range(3)}
    return all(math.dist(points[a],points[b])<=2*math.dist(reference[a],reference[b]) for a,b in edges)


def select(reference,current,moves,anchors,targets,triangles):
    if not geometry(reference,current,triangles):raise ValueError('increment_baseline_geometry_failed')
    baseline=sum(x*x+y*y for x,y in targets);maximum=max(math.hypot(*m) for m in moves)
    cap=min(1.,2/maximum) if maximum else 1.
    for step in range(13):
        scale=cap*2**(-step);delta=[[v*scale for v in m] for m in moves]
        points=[[p[k]+d[k] for k in (0,1)] for p,d in zip(current,delta)]
        error=sum((position(a,delta)[k]-target[k])**2 for a,target in zip(anchors,targets) for k in (0,1))
        if geometry(reference,points,triangles) and error<=baseline+1e-10:
            return delta,{'scale':scale,'backtracks':step,'residual_before':baseline,'residual_after':error,'status':'candidate'}
    return [[0.,0.] for _ in current],{'scale':0.,'backtracks':13,'residual_before':baseline,'residual_after':baseline,'status':'retained_baseline'}


def solve(reference,current,anchors,targets,triangles,chains):
    moves,initial=proposal(current,anchors,targets,triangles,chains)
    delta,qa=select(reference,current,moves,anchors,targets,triangles)
    qa['proposal_backtracks']=initial['backtracks'];qa['max_increment_px']=max(math.hypot(*d) for d in delta)
    return delta,qa
