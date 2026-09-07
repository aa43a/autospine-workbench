"""Bounded deterministic area/edge projection on an auxiliary elbow preview."""
import math
from .elbow_alternatives import deform, validate_source
from .mesh_weights import _area, evaluate_mesh

ITERATIONS = 48
AREA_BOUNDS = (.55, 1.9)
EDGE_LIMIT = 1.9


def prepare(row, bones):
    vertices, triangles, weights = row['vertices_xy'], row['triangles'], row['weights']
    validate_source(vertices,weights,bones)
    evaluate_mesh(vertices,triangles,weights,bones)
    areas = [_area(vertices,t) for t in triangles]
    if any(abs(a) <= 1e-9 for a in areas):raise ValueError('elbow_constraints_degenerate_setup')
    edges = sorted({tuple(sorted((a,b))) for t in triangles for a,b in zip(t,t[1:]+t[:1])})
    return {'row':row,'bones':bones,'areas':areas,'edges':edges,
            'lengths':[math.dist(vertices[a],vertices[b]) for a,b in edges],
            'free':[0 < w[1]['weight']+w[2]['weight'] < 1 for w in weights],
            'max_offset':.1*min(b['length'] if 'length' in b else math.dist(b['head_xy'],b['tail_xy']) for b in bones[:2])}


def solve(context, angle):
    row, bones = context['row'], context['bones']
    base = deform(row['vertices_xy'],row['weights'],bones,angle,'half_angle_auxiliary')
    points = [p[:] for p in base]
    if angle == 0:return points
    free = context['free']
    for _ in range(ITERATIONS):
        for tri, area in zip(row['triangles'],context['areas']):
            ratio = _area(points,tri)/area
            target = max(AREA_BOUNDS[0],min(AREA_BOUNDS[1],ratio))
            if ratio == target:continue
            a,b,c = [points[i] for i in tri]
            gradients = [[(b[1]-c[1])/2,(c[0]-b[0])/2],
                         [(c[1]-a[1])/2,(a[0]-c[0])/2],
                         [(a[1]-b[1])/2,(b[0]-a[0])/2]]
            denominator = sum(sum(v*v for v in g) for i,g in zip(tri,gradients) if free[i])
            if denominator <= 1e-18:continue
            scale = (target-ratio)*area/denominator
            for i,g in zip(tri,gradients):
                if free[i]:
                    for axis in (0,1):points[i][axis] += scale*g[axis]
        for (a,b),length in zip(context['edges'],context['lengths']):
            delta = [points[b][i]-points[a][i] for i in (0,1)]
            distance = math.hypot(*delta)
            count = int(free[a])+int(free[b])
            if not count or distance <= EDGE_LIMIT*length:continue
            scale = (distance-EDGE_LIMIT*length)/distance/count
            for i in (0,1):
                if free[a]:points[a][i] += scale*delta[i]
                if free[b]:points[b][i] -= scale*delta[i]
        # Fixed displacement budget prevents a quality metric from moving the whole limb.
        for index,(point,origin) in enumerate(zip(points,base)):
            if not free[index]:continue
            distance = math.dist(point,origin)
            if distance > context['max_offset']:
                points[index] = [origin[i]+(point[i]-origin[i])*context['max_offset']/distance for i in (0,1)]
    if not all(math.isfinite(v) for p in points for v in p):raise ValueError('elbow_constraints_nonfinite')
    return points
