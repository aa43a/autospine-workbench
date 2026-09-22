"""One-surface material transport through a fixed piecewise affine UV map."""
import numpy as np


def build(source_uv, mapped_uv, triangles, *, max_extrapolation=.75, preserve_unmapped=False):
    queries=np.asarray(source_uv,float).reshape(-1,2)
    mapped=np.asarray(mapped_uv,float).reshape(-1,2)
    tri=np.asarray(triangles,int).reshape(-1,3)
    if (mapped.shape!=queries.shape or not len(tri) or not len(queries)
            or not np.isfinite(queries).all() or not np.isfinite(mapped).all()
            or tri.min()<0 or tri.max()>=len(queries) or not 0<=max_extrapolation<=1):
        raise ValueError('material_transport_input')
    best=np.full(len(queries),np.inf);indices=np.zeros((len(queries),3),int)
    coefficients=np.zeros((len(queries),3))
    for ids in tri:
        a,b,c=mapped[ids];matrix=np.column_stack((b-a,c-a))
        if abs(np.linalg.det(matrix))<1e-12:raise ValueError('material_transport_degenerate_uv')
        coordinates=(queries-a)@np.linalg.inv(matrix).T
        weights=np.column_stack((1-coordinates.sum(axis=1),coordinates))
        penalty=np.maximum(0,-weights).sum(axis=1)
        update=penalty<best-1e-10
        indices[update]=ids;coefficients[update]=weights[update];best[update]=penalty[update]
    unsupported=np.flatnonzero(best>max_extrapolation)
    if len(unsupported) and not preserve_unmapped:raise ValueError('material_transport_extrapolation_limit')
    # Explicit partial experiment: unsupported vertices retain their original motion.
    for index in unsupported:
        indices[index]=index;coefficients[index]=[1,0,0]
    return dict(indices=indices.tolist(),weights=coefficients.tolist(),
                extrapolated_vertices=int(np.count_nonzero((best>1e-8)&(best<=max_extrapolation))),
                maximum_extrapolation=float(np.where(best<=max_extrapolation,best,0).max()),
                maximum_required_extrapolation=float(best.max()),
                preserved_unmapped_vertices=unsupported.tolist(),authority='none')


def apply(points, mapping, blend):
    points=np.asarray(points,float);indices=np.asarray(mapping['indices'],int)
    weights=np.asarray(mapping['weights'],float)
    if (not np.isfinite(points).all() or not np.isfinite(blend) or not 0<=blend<=1
            or indices.shape!=(len(points),3) or weights.shape!=indices.shape
            or not np.isfinite(weights).all() or indices.min()<0 or indices.max()>=len(points)):
        raise ValueError('material_transport_pose')
    target=np.einsum('ij,ijk->ik',weights,points[indices])
    return (points+(target-points)*blend).tolist()
