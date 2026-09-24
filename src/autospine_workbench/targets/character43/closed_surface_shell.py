"""Diagnostic extrusion with explicit untextured sides; not anatomical recovery."""
from collections import defaultdict
import numpy as np


def build(vertices, triangles, thickness):
    p=np.asarray(vertices,float);t=np.asarray(triangles)
    if (p.ndim!=2 or p.shape[1]!=3 or not np.isfinite(p).all() or t.ndim!=2 or t.shape[1]!=3 or
            not t.size or not np.issubdtype(t.dtype,np.integer) or t.min()<0 or t.max()>=len(p) or
            not np.isfinite(thickness) or thickness<=0):raise ValueError('shell_input')
    signed=np.cross(p[t[:,1]]-p[t[:,0]],p[t[:,2]]-p[t[:,0]])[:,2]
    if (abs(signed)<1e-10).any() or not ((signed>0).all() or (signed<0).all()):
        raise ValueError('shell_requires_consistent_front_winding')
    front=t.copy() if signed[0]>0 else t[:,::-1].copy()
    edges=defaultdict(list)
    for face in front:
        for a,b in zip(face,np.roll(face,-1)):edges[tuple(sorted((int(a),int(b))))].append((int(a),int(b)))
    if any(len(e)>2 or (len(e)==2 and e[0]!=e[1][::-1]) for e in edges.values()):
        raise ValueError('shell_nonmanifold_front_edges')
    boundary=[e[0] for e in edges.values() if len(e)==1]
    if not boundary:raise ValueError('shell_front_has_no_boundary')
    n=len(p);faces=front.tolist()+(front[:,::-1]+n).tolist()
    roles=['original_front']*len(front)+['missing_back_material']*len(front)
    for a,b in boundary:
        faces.extend([[a,a+n,b+n],[a,b+n,b]])
        roles.extend(['missing_side_material']*2)
    closed=defaultdict(list)
    for face in faces:
        for a,b in zip(face,face[1:]+face[:1]):closed[tuple(sorted((a,b)))].append((a,b))
    if any(len(e)!=2 or e[0]!=e[1][::-1] for e in closed.values()):raise ValueError('shell_open_edges')
    return dict(vertices=np.concatenate((p,p-[0,0,thickness])).tolist(),triangles=faces,
                material_roles=roles,source_front_vertex_count=n,thickness=thickness,
                boundary_edges=len(boundary),closed_oriented_edges=True,accepted=False,
                limitations=['extrusion_is_hypothesis_not_anatomy','alpha_margin_is_not_body_volume',
                             'side_and_back_material_missing','self_intersection_not_checked'])
