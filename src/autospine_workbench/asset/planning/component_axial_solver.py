"""Distal axial-band experiment; unchanged budget and fixed vertices outside the band."""
import math
from .component_local_solver import metrics
from ..joints.mesh_weights import _area
from ..joints.joint_plane_weights import _planes


def solve(mesh, original, initial, bones, joint):
    if joint != 2: return initial, dict(reason='root_fixed',free_vertices=[],budget=0.)
    triangles=mesh['triangles'];setup=mesh['vertices_xy']
    qa=metrics(setup,initial,triangles)
    bad={v for i in qa['bad_triangles'] for v in triangles[i]}
    ring={v for t in triangles if any(v in bad for v in t) for v in t}
    length=min(math.dist(b['head_xy'],b['tail_xy']) for b in bones[joint-1:joint+1])
    # Distal bone length describes fingers/toes, not the width of a wrist/ankle collar.
    if joint==2:
        length=math.dist(bones[joint-1]['head_xy'],bones[joint-1]['tail_xy'])
    budget=.15*length;radius=(.45 if joint==2 else .55)*length;pivot=bones[joint]['head_xy']
    # Keep a bounded axial interval; transverse support comes from this isolated region only.
    normal=_planes(bones)[1][1]
    free={i for i in ring if abs(sum((setup[i][k]-pivot[k])*normal[k] for k in (0,1)))<=radius}
    points=[p[:] for p in initial]
    areas=[_area(setup,t) for t in triangles]
    edges=sorted({tuple(sorted((a,b))) for t in triangles for a,b in zip(t,t[1:]+t[:1])})
    for _ in range(96):
        for t,area in zip(triangles,areas):
            ratio=_area(points,t)/area;target=max(.55,min(1.9,ratio))
            if ratio==target:continue
            a,b,c=[points[i] for i in t]
            gradients=[[(b[1]-c[1])/2,(c[0]-b[0])/2],[(c[1]-a[1])/2,(a[0]-c[0])/2],[(a[1]-b[1])/2,(b[0]-a[0])/2]]
            divisor=sum(sum(v*v for v in g) for i,g in zip(t,gradients) if i in free)
            if divisor<1e-18:continue
            for i,g in zip(t,gradients):
                if i in free:
                    for k in (0,1):points[i][k]+=(target-ratio)*area*g[k]/divisor
        for a,b in edges:
            distance=math.dist(points[a],points[b]);limit=1.9*math.dist(setup[a],setup[b])
            count=int(a in free)+int(b in free)
            if count and distance>limit:
                delta=[(points[b][k]-points[a][k])*(distance-limit)/distance/count for k in (0,1)]
                for k in (0,1):
                    if a in free:points[a][k]+=delta[k]
                    if b in free:points[b][k]-=delta[k]
        for i in free:
            distance=math.dist(points[i],original[i])
            if distance>budget:points[i]=[original[i][k]+(points[i][k]-original[i][k])*budget/distance for k in (0,1)]
    if any(not math.isfinite(v) for p in points for v in p):raise ValueError('collar_nonfinite')
    after=metrics(setup,points,triangles)
    allowed=(after['inversions']<=qa['inversions'] and set(after['bad_triangles'])<=set(qa['bad_triangles'])
             and after['max_edge_stretch']<=max(2,qa['max_edge_stretch'])
             and (after['inversions']<qa['inversions'] or len(after['bad_triangles'])<len(qa['bad_triangles'])))
    return (points if allowed else initial),dict(reason='local_improvement' if allowed else 'kept_previous',
        free_vertices=sorted(free),budget=budget,axial_halfwidth=radius,trial_qa=after,
        added_transverse_vertices=sum(math.dist(setup[i],pivot)>radius for i in free),
        max_offset=max((math.dist(points[i],original[i]) for i in free),default=0.))
