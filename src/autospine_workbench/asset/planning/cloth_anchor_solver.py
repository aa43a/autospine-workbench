"""Bounded area/edge correction with explicit cloth-only freedom and fixed anchors."""
import math
from .component_local_solver import metrics
from ..joints.mesh_weights import _area


def solve(setup,triangles,points,cloth_vertices,anchors,budget,*,seed=None):
    if not math.isfinite(budget) or budget<=0 or len(setup)!=len(points):raise ValueError('cloth_anchor_input')
    indices=set(range(len(points)));free=set(cloth_vertices)-set(anchors)
    if (not points or not set(cloth_vertices)<=indices or not set(anchors)<=indices
            or any(len(p)!=2 or any(not math.isfinite(v) for v in p) for p in setup+points)
            or any(len(t)!=3 or len(set(t))!=3 or not set(t)<=indices for t in triangles)):
        raise ValueError('cloth_anchor_input')
    moved=[p[:] for p in points];areas=[_area(setup,t) for t in triangles]
    if seed is not None:
        if len(seed)!=len(points) or any(len(p)!=2 or any(not math.isfinite(v) for v in p) for p in seed):
            raise ValueError('cloth_anchor_seed')
        for i in free:
            distance=math.dist(points[i],seed[i]);scale=min(1.,budget/distance) if distance else 1.
            moved[i]=[points[i][k]+(seed[i][k]-points[i][k])*scale for k in (0,1)]
    if any(abs(a)<1e-9 for a in areas):raise ValueError('cloth_anchor_degenerate')
    edges=sorted({tuple(sorted((a,b))) for t in triangles for a,b in zip(t,t[1:]+t[:1])})
    for _ in range(48):
        for tri,area in zip(triangles,areas):
            ratio=_area(moved,tri)/area;target=max(.55,min(1.9,ratio))
            if target==ratio:continue
            a,b,c=[moved[i] for i in tri]
            grads=[[(b[1]-c[1])/2,(c[0]-b[0])/2],[(c[1]-a[1])/2,(a[0]-c[0])/2],[(a[1]-b[1])/2,(b[0]-a[0])/2]]
            den=sum(sum(x*x for x in g) for i,g in zip(tri,grads) if i in free)
            if den<1e-18:continue
            for i,g in zip(tri,grads):
                if i in free:
                    for k in (0,1):moved[i][k]+=(target-ratio)*area*g[k]/den
        for a,b in edges:
            distance=math.dist(moved[a],moved[b]);limit=1.9*math.dist(setup[a],setup[b]);count=int(a in free)+int(b in free)
            if count and distance>limit:
                delta=[(moved[b][k]-moved[a][k])*(distance-limit)/distance/count for k in (0,1)]
                for k in (0,1):
                    if a in free:moved[a][k]+=delta[k]
                    if b in free:moved[b][k]-=delta[k]
        for i in free:
            d=math.dist(points[i],moved[i])
            if d>budget:moved[i]=[points[i][k]+(moved[i][k]-points[i][k])*budget/d for k in (0,1)]
    if any(not math.isfinite(v) for p in moved for v in p):raise ValueError('cloth_anchor_nonfinite')
    return moved,dict(free_vertices=sorted(free),anchor_vertices=sorted(set(anchors)),budget_px=budget,
                     max_offset=max(math.dist(a,b) for a,b in zip(points,moved)),qa=metrics(setup,moved,triangles))
