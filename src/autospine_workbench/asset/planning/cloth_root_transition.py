"""Geodesic cloth-root attenuation with unchanged non-cloth vertices."""
from copy import deepcopy
import heapq
import math
from ..joints.mesh_weights import _rotate


def reweight(mesh, chain, helper, cloth_vertices):
    vertices=mesh['vertices_xy'];cloth=set(cloth_vertices)
    neighbors=[set() for _ in vertices]
    for tri in mesh['triangles']:
        for i in tri:neighbors[i].update(j for j in tri if j!=i)
    # Sources are the fixed interface, not the canvas or Euclidean-nearest unrelated fabric.
    boundary={j for i in cloth for j in neighbors[i] if j not in cloth}
    distances=[math.inf]*len(vertices);queue=[]
    for i in sorted(boundary):distances[i]=0.;heapq.heappush(queue,(0.,i))
    while queue:
        distance,i=heapq.heappop(queue)
        if distance!=distances[i]:continue
        for j in sorted(neighbors[i]):
            if j not in cloth:continue
            trial=distance+math.dist(vertices[i],vertices[j])
            if trial<distances[j]:distances[j]=trial;heapq.heappush(queue,(trial,j))
    width=.25*math.dist(chain[1]['head_xy'],chain[1]['tail_xy'])
    if not math.isfinite(width) or width<=1e-6:raise ValueError('cloth_transition_degenerate')
    weights=deepcopy(mesh['weights']);factors={};unreachable=[]
    for i in sorted(cloth):
        if not math.isfinite(distances[i]):unreachable.append(i);continue
        t=min(1.,distances[i]/width);factor=t*t*(3-2*t);factors[str(i)]=factor
        row=weights[i];downstream=sum(w['weight'] for w in row if w['bone_id'] in (chain[1]['id'],chain[2]['id']))
        weights[i]=[w for w in row if w['bone_id'] not in (chain[1]['id'],chain[2]['id'])]
        for bone,weight in [(chain[1],downstream*(1-factor)),(helper,downstream*factor)]:
            weights[i].append(dict(bone_id=bone['id'],weight=weight,
                local_xy=_rotate([vertices[i][k]-bone['head_xy'][k] for k in (0,1)],-bone['world_rotation_degrees'])))
    return weights,dict(profile='cloth-geodesic-quarter-parent-v1',width_px=width,
        fixed_boundary_vertices=sorted(boundary),helper_factors=factors,unreachable_vertices=unreachable)
