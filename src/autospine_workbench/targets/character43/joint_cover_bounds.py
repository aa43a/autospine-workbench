"""Bound uniform joint-cover growth by support and existing geometry limits."""
import math
import numpy as np
from scipy.spatial import ConvexHull, QhullError


def cover(points, center, targets, maximum_scale, *, padding=0.):
    p=np.asarray(points,float);c=np.asarray(center,float);q=np.asarray(targets,float)
    if (p.ndim!=2 or p.shape[1]!=2 or len(p)<3 or q.ndim!=2 or q.shape[1]!=2 or not len(q)
            or c.shape!=(2,) or not all(np.isfinite(a).all() for a in (p,c,q))
            or not math.isfinite(maximum_scale) or maximum_scale<1 or not math.isfinite(padding) or padding<0):
        raise ValueError('joint_cover_input')
    try:hull=ConvexHull(p-c)
    except QhullError as exc:raise ValueError('joint_cover_degenerate') from exc
    normals=hull.equations[:,:2];distances=-hull.equations[:,2]
    if distances.min()<=1e-8:raise ValueError('joint_cover_center_outside')
    required=max(1.,float((((q-c)@normals.T+padding)/distances).max()))
    # Keep numerical headroom within the caller's explicit geometry budget.
    scale=min(maximum_scale,required+1e-9) if required<=maximum_scale else 1.
    admissible=required<=maximum_scale
    result=c+scale*(p-c)
    remaining=max(0.,float(((q-c)@normals.T+padding-scale*distances).max()))
    return result.tolist(),dict(status='bounded_geometric_cover' if admissible else 'coverage_exceeds_geometry_budget',
        required_scale=required,applied_scale=scale,maximum_scale=maximum_scale,
        maximum_boundary_deficit_px=remaining,scope='convex_geometry_not_alpha_coverage',selected=False)
