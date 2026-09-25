"""Track material landmarks inside triangles, not nearby transparent vertices.

This is positional evidence only. Sliding occlusion still needs alpha and
draw-order checks; landmark distance is not a visible-crack decision.
"""
import numpy as np


def _mesh(points, triangles):
    p = np.asarray(points, dtype=float); raw = np.asarray(triangles)
    if (p.ndim != 2 or p.shape[1:] != (2,) or len(p) < 3 or not np.isfinite(p).all()
            or raw.ndim != 2 or raw.shape[1:] != (3,) or not len(raw)
            or raw.dtype.kind not in 'iu' or raw.min() < 0 or raw.max() >= len(p)):
        raise ValueError('material_contact_mesh_invalid')
    return p, raw.astype(int)


def bind(points, triangles, locations):
    p, tri = _mesh(points, triangles)
    probes = np.asarray(locations, dtype=float)
    if probes.ndim != 2 or probes.shape[1:] != (2,) or not len(probes) or not np.isfinite(probes).all():
        raise ValueError('material_contact_locations_invalid')
    a=p[tri[:,0]]; u=p[tri[:,1]]-a; v=p[tri[:,2]]-a
    det=u[:,0]*v[:,1]-u[:,1]*v[:,0]
    usable=np.abs(det)>1e-10
    records=[]
    for point in probes:
        delta=point-a
        b=np.divide(delta[:,0]*v[:,1]-delta[:,1]*v[:,0],det,out=np.zeros(len(tri)),where=usable)
        c=np.divide(u[:,0]*delta[:,1]-u[:,1]*delta[:,0],det,out=np.zeros(len(tri)),where=usable)
        weights=np.column_stack((1-b-c,b,c))
        hits=np.flatnonzero(usable & (weights.min(axis=1)>=-1e-9))
        if not len(hits):raise ValueError('material_contact_point_outside_mesh')
        # Shared-edge hits choose a stable triangle. Interior overlap is ambiguous.
        if sum(weights[i].min()>1e-9 for i in hits)>1:
            raise ValueError('material_contact_overlapping_mesh')
        if len(hits)>1:
            signatures=[]
            for hit in hits:
                signature=np.zeros(len(p))
                np.add.at(signature,tri[hit],weights[hit])
                signatures.append(signature)
            if any(not np.allclose(signatures[0],s,rtol=0,atol=1e-9) for s in signatures[1:]):
                raise ValueError('material_contact_overlapping_mesh')
        i=int(hits[0]); w=np.maximum(weights[i],0); w/=w.sum()
        if np.linalg.norm(w@p[tri[i]]-point)>1e-7:
            raise ValueError('material_contact_reconstruction_failed')
        records.append(dict(triangle=i, weights=w.tolist(), setup=point.tolist()))
    return dict(vertex_count=len(p),triangles=tri.tolist(),records=records)


def sample(binding, points, triangles):
    p,tri=_mesh(points,triangles)
    if binding['vertex_count']!=len(p) or binding['triangles']!=tri.tolist():
        raise ValueError('material_contact_topology_changed')
    result=[]
    for row in binding['records']:
        i=row['triangle']; w=np.asarray(row['weights'],dtype=float)
        if (type(i) is not int or not 0<=i<len(tri) or w.shape!=(3,)
                or not np.isfinite(w).all() or w.min()<0 or abs(w.sum()-1)>1e-9):
            raise ValueError('material_contact_binding_invalid')
        result.append((w@p[tri[i]]).tolist())
    return result
